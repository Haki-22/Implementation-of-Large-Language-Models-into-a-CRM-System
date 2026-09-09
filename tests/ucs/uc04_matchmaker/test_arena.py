"""UC-04 arena: the database reader, both protocols and the arm interface on a toy substrate.

A five-customer, eight-product SQLite file with the three tables the arena reads
(``uc_contacts``, ``uc_reviews``, ``uc_products``) is enough to pin down what the
code must never get wrong: which review is hidden, how a same-day tie breaks, that
prospects fall out, that the Czech branch keeps the same split, that the sampled
protocol never puts a bought product among the negatives, and that hits are
counted from ranks the way the card reports them.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from ucs.uc04_matchmaker import attachment, facts, protocols
from ucs.uc04_matchmaker.arena import run
from ucs.uc04_matchmaker.arms import ARMS, als_cf, popularity, resolve
from ucs.uc04_matchmaker.data import load_arena

PRODUCTS = [
    ("P1", "Cable"),
    ("P2", "Mouse"),
    ("P3", "Keyboard"),
    ("P4", "Monitor"),
    ("P5", "Headset"),
    ("P6", "Webcam"),
    ("P7", "Speaker"),
    ("P8", "Charger"),
]
# (contact, group, [(product, rating, date)]) — the last by (date, id) is hidden.
CUSTOMERS = [
    (
        1,
        "A",
        [
            ("P1", 5, "2013-01-01"),
            ("P2", 4, "2013-02-01"),
            ("P3", 5, "2013-03-01"),
            ("P4", 3, "2013-04-01"),
        ],
    ),
    (
        2,
        "A",
        [
            ("P1", 4, "2013-01-05"),
            ("P2", 5, "2013-02-05"),
            ("P4", 4, "2013-03-05"),
            ("P5", 5, "2013-03-05"),
        ],
    ),  # same-day tie
    (3, "B", [("P2", 5, "2013-01-10"), ("P3", 4, "2013-02-10"), ("P6", 2, "2013-05-10")]),
    (4, "C", [("P1", 3, "2013-01-15"), ("P4", 4, "2013-02-15")]),
    (5, "C", [("P7", 5, "2013-01-20")]),  # one review only: no history left
]


@pytest.fixture()
def toy_db(tmp_path: Path) -> Path:
    """A five-customer, eight-product SQLite file (``CUSTOMERS``/``PRODUCTS``) under ``tmp_path``."""
    path = tmp_path / "substrate.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE uc_contacts (id INTEGER PRIMARY KEY, reviewer_id TEXT, amazon_group TEXT);
        CREATE TABLE uc_products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, name_cs TEXT, category TEXT, description TEXT, price REAL);
        CREATE TABLE uc_reviews (id INTEGER PRIMARY KEY, contact_id INTEGER, product_id INTEGER, rating REAL,
                                 review_date TEXT, summary_en TEXT, text_en TEXT, summary_cs TEXT, text_cs TEXT);
        """
    )
    for i, (sku, name) in enumerate(PRODUCTS, start=1):
        conn.execute(
            "INSERT INTO uc_products VALUES (?,?,?,?,?,?,?)",
            (i, sku, name, f"{name}-cs", "Accessories", f"A {name.lower()}", 9.9),
        )
    conn.execute(
        "INSERT INTO uc_contacts VALUES (99, NULL, NULL)"
    )  # a prospect: no reviewer, no reviews
    rid = 0
    for cid, group, reviews in CUSTOMERS:
        conn.execute("INSERT INTO uc_contacts VALUES (?,?,?)", (cid, f"R{cid}", group))
        for sku, rating, day in reviews:
            rid += 1
            pid = [p for p, _ in PRODUCTS].index(sku) + 1
            conn.execute(
                "INSERT INTO uc_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    cid,
                    pid,
                    rating,
                    day,
                    "ok",
                    f"english {sku}",
                    "ok cs",
                    f"cesky {sku}" if sku != "P4" else "",
                ),
            )
    conn.commit()
    conn.close()
    return path


def test_split_hides_the_last_review_and_drops_prospects_and_singletons(toy_db: Path) -> None:
    arena = load_arena("en", toy_db)
    assert [c.contact_id for c in arena.customers] == [
        1,
        2,
        3,
        4,
    ]  # 5 has one review, 99 is a prospect
    c1 = arena.customers[0]
    assert c1.held_out.asin == "P4" and c1.history_asins == {"P1", "P2", "P3"}
    assert arena.n_items == 8 and arena.all_asins == sorted(p for p, _ in PRODUCTS)


def test_same_day_tie_breaks_by_lowest_review_id(toy_db: Path) -> None:
    arena = load_arena("en", toy_db)
    c2 = next(c for c in arena.customers if c.contact_id == 2)
    assert (
        c2.held_out.asin == "P5"
    )  # P4 and P5 share the day; P5 has the higher id, so it is the later one
    assert "P4" in c2.history_asins


def test_czech_branch_keeps_the_split_and_swaps_only_the_text(toy_db: Path) -> None:
    en, cs = load_arena("en", toy_db), load_arena("cs", toy_db)
    assert [c.held_out.asin for c in en.customers] == [c.held_out.asin for c in cs.customers]
    assert [c.history_asins for c in en.customers] == [c.history_asins for c in cs.customers]
    texts = {it.asin: it.text for it in cs.customers[0].history}
    assert texts["P1"] == "cesky P1" and texts["P2"] == "cesky P2"
    assert en.catalog["P1"]["title"] == "Cable" and cs.catalog["P1"]["title_cs"] == "Cable-cs"


def test_full_protocol_counts_hits_from_the_rank(toy_db: Path) -> None:
    arena = load_arena("en", toy_db)
    scores = np.zeros((arena.n_customers, arena.n_items), dtype=np.float32)
    # give customer 1 its hidden item (P4) the top score, customer 3 its hidden item (P6) rank 6 of the unbought
    scores[0, arena.asin_to_idx["P4"]] = 10.0
    for j, asin in enumerate(["P1", "P4", "P5", "P7", "P8"]):
        scores[2, arena.asin_to_idx[asin]] = 5.0 - j
    # customer 2 (hidden P5): four unbought products above it -> rank 5; customer 4 (hidden P4): rank 7
    for j, asin in enumerate(["P3", "P6", "P7", "P8"]):
        scores[1, arena.asin_to_idx[asin]] = 4.0 - j
    for j, asin in enumerate(["P2", "P3", "P5", "P6", "P7", "P8"]):
        scores[3, arena.asin_to_idx[asin]] = 6.0 - j
    res = protocols.evaluate_full(scores, arena, reach_ks=(3,))
    ranks = {d["contact_id"]: d["rank"] for d in res.per_customer}
    assert ranks == {1: 1, 2: 5, 3: 6, 4: 7}
    assert res.hits[5] == 2 and res.hits[10] == 4
    assert res.reach[3] == 1
    assert (
        "P1" not in [d for d in res.per_customer if d["contact_id"] == 1][0]["top10"]
    )  # history is masked


def test_sampled_candidates_are_fixed_unbought_and_include_the_hidden_item(toy_db: Path) -> None:
    arena = load_arena("en", toy_db)
    cands = protocols.sample_candidates(arena, n_neg=3, seed=7)
    again = protocols.sample_candidates(arena, n_neg=3, seed=7)
    assert cands == again
    for c, lst in zip(arena.customers, cands):
        assert len(lst) == 4 and arena.all_asins[lst[-1]] == c.held_out.asin
        negatives = {arena.all_asins[j] for j in lst[:-1]}
        assert not (negatives & c.history_asins) and c.held_out.asin not in negatives
    scores = np.zeros((arena.n_customers, arena.n_items), dtype=np.float32)
    scores[:, arena.asin_to_idx["P4"]] = (
        1.0  # everyone loves P4 → customer 1 (hidden P4) ranks it first
    )
    res = protocols.evaluate_sampled(scores, arena, cands, seed=1)
    assert {d["contact_id"]: d["rank"] for d in res.per_customer}[1] == 1
    assert protocols.random_floor("sampled", arena.n_items, 3, k=1) == pytest.approx(0.25)


def test_registry_and_the_arm_interface(toy_db: Path) -> None:
    assert resolve("fast") and set(resolve("population")) <= set(ARMS)
    with pytest.raises(ValueError):
        resolve("no_such_arm")
    arena = load_arena("en", toy_db)
    pop = popularity.score(arena)
    assert pop.shape == (arena.n_customers, arena.n_items)
    assert (
        pop[0, arena.asin_to_idx["P1"]] == 3.0
    )  # P1 bought by customers 1, 2, 4 (5 is not in the arena)
    als = als_cf.score(arena)
    assert als.shape == pop.shape and np.isfinite(als).all()


def test_run_writes_a_complete_run_folder(toy_db: Path, tmp_path: Path) -> None:
    run_dir = run(
        arms=["popularity", "als_cf"],
        langs=["en", "cs"],
        regimes=["crm"],
        n_neg=3,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        label="toy",
        attachments_dir=tmp_path / "attachments",
    )
    assert (
        (run_dir / "config.json").exists()
        and (run_dir / "TABLE.md").exists()
        and (run_dir / "RESULTS.md").exists()
    )
    assert sorted(p.name for p in (run_dir / "scores").glob("*.json")) == [
        "crm-als_cf-cs.json",
        "crm-als_cf-en.json",
        "crm-popularity-cs.json",
        "crm-popularity-en.json",
    ]
    card = (run_dir / "RESULTS.md").read_text(encoding="utf-8")
    assert "Model calls: none" in card and "protocol full" in card and "protocol sampled" in card
    assert (tmp_path / "runs" / "README.md").exists()


def test_facts_run_writes_the_numbers_the_card_quotes(toy_db: Path, tmp_path: Path) -> None:
    run_dir = facts.run(
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        label="toy-facts",
        attachments_dir=tmp_path / "attachments",
    )
    payload = json.loads((run_dir / "facts.json").read_text(encoding="utf-8"))
    f = {k: v["value"] for k, v in payload["facts"].items()}
    assert f["customers_linked"] == 4 and f["customers_prospects"] == 1
    assert f["catalogue_products"] == 8 and f["catalogue_czech_titles"] == 8
    assert f["last_day_ties"] == 1  # customer 2
    # hidden items: P4 (c1 and c4) sits in c2's history -> one other buyer each; P5 (c2) and P6 (c3) in nobody's
    assert f["hidden_bought_by_0_others"] == 2 and f["hidden_bought_by_1_other"] == 2
    assert (run_dir / "facts.csv").exists()
    assert "Model calls: none" in (run_dir / "RESULTS.md").read_text(encoding="utf-8")
    assert (tmp_path / "attachments" / "uc04-data-facts.md").exists()  # refreshed by the run itself


def test_partial_run_keeps_the_appendix_and_build_takes_exactly_one_folder(
    toy_db: Path, tmp_path: Path
) -> None:
    runs, att = tmp_path / "runs", tmp_path / "attachments"
    first = run(
        arms=["popularity", "als_cf"],
        langs=["en", "cs"],
        regimes=["crm"],
        n_neg=3,
        db_path=toy_db,
        base_dir=runs,
        label="toy-two-arms",
        attachments_dir=att,
    )
    assert not (att / "uc04-arena-results.csv").exists()  # two of twelve arms: not a run of record
    assert (first / "TABLE.md").exists()  # the folder's own readable output
    written = attachment.build(run_dir=first, out_dir=att)  # by hand, one folder
    rows = list(csv.DictReader(open(att / "uc04-arena-results.csv", encoding="utf-8")))
    assert len(rows) == 2 * 2 * 2 and {r["run"] for r in rows} == {first.name}
    md = (att / "uc04-arena-results.md").read_text(encoding="utf-8")
    assert "Tabulka 1" in md and first.name in md and "`als_cf`" in md
    again = attachment.build(run_dir=first, out_dir=tmp_path / "attachments2")
    for a, b in zip(written, again):
        assert a.read_bytes() == b.read_bytes()  # reproducible byte for byte
    assert attachment.newest_full_run(runs) is None


def test_a_comparison_folder_is_never_the_record() -> None:
    """A demo-page run (role comparison) covering every arm must not become the record."""
    from ucs.uc04_matchmaker import arms as arm_registry
    from ucs.uc04_matchmaker import attachment

    every_arm = {name: {} for name in arm_registry.ARMS}
    assert attachment.is_full_run({"arms": every_arm}) is True
    assert attachment.is_full_run({"arms": every_arm, "role": "record"}) is True
    assert attachment.is_full_run({"arms": every_arm, "role": "comparison"}) is False
