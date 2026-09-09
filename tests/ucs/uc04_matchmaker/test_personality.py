"""UC-04 personality feature: the profile columns, the paired statistics and the run folder, on a toy substrate.

What must never go wrong: the five columns appear only when a mapping is given and a
customer without a profile gets the missing value; the pairing counts discordant pairs
on aligned customer lists and refuses misaligned ones; a run writes one score file per
arm × variant × branch, the pairs, the tables, the card and the attachment pair.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from ucs.uc04_matchmaker import personality
from ucs.uc04_matchmaker.arms._features import MIDPOINT, TRAITS, FeatureTable
from ucs.uc04_matchmaker.data import load_arena

PRODUCTS = [f"P{i}" for i in range(1, 9)]
# (contact, group, [(product, rating, date)], inferred profile?) — the last by date is hidden.
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
        True,
    ),
    (
        2,
        "A",
        [
            ("P1", 4, "2013-01-05"),
            ("P2", 5, "2013-02-05"),
            ("P4", 4, "2013-03-05"),
            ("P5", 5, "2013-03-06"),
        ],
        True,
    ),
    (3, "B", [("P2", 5, "2013-01-10"), ("P3", 4, "2013-02-10"), ("P6", 2, "2013-05-10")], True),
    (4, "C", [("P1", 3, "2013-01-15"), ("P4", 4, "2013-02-15"), ("P7", 4, "2013-03-15")], False),
]
PROFILE = {"O": 4.0, "C": 3.5, "E": 3.0, "A": 4.5, "N": 2.0}


@pytest.fixture()
def toy(tmp_path: Path) -> tuple[Path, Path]:
    """A toy substrate with the OCEAN columns, and a sampled-profile snapshot for two customers."""
    db = tmp_path / "substrate.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE uc_contacts (id INTEGER PRIMARY KEY, reviewer_id TEXT, amazon_group TEXT, ocean TEXT, ocean_source TEXT);
        CREATE TABLE uc_products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, name_cs TEXT, category TEXT, description TEXT, price REAL);
        CREATE TABLE uc_reviews (id INTEGER PRIMARY KEY, contact_id INTEGER, product_id INTEGER, rating REAL,
                                 review_date TEXT, summary_en TEXT, text_en TEXT, summary_cs TEXT, text_cs TEXT);
        """
    )
    for i, sku in enumerate(PRODUCTS, start=1):
        conn.execute(
            "INSERT INTO uc_products VALUES (?,?,?,?,?,?,?)",
            (i, sku, f"Product {i}", f"Produkt {i}", "Cat" if i % 2 else "Other", "d" * i, 9.9),
        )
    rid = 0
    for cid, group, reviews, inferred in CUSTOMERS:
        conn.execute(
            "INSERT INTO uc_contacts VALUES (?,?,?,?,?)",
            (
                cid,
                f"R{cid}",
                group,
                json.dumps(PROFILE) if inferred else None,
                "inferred" if inferred else None,
            ),
        )
        for sku, rating, day in reviews:
            rid += 1
            conn.execute(
                "INSERT INTO uc_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, cid, PRODUCTS.index(sku) + 1, rating, day, "s", "t", "s", "t"),
            )
    conn.commit()
    conn.close()
    synthetic = tmp_path / "ocean_synthetic.json"
    synthetic.write_text(
        json.dumps(
            {
                "rows": [
                    {"contact_id": 1, "ocean": {"O": 3.0, "C": 3.0, "E": 3.0, "A": 3.0, "N": 3.0}},
                    {"contact_id": 4, "ocean": {"O": 2.0, "C": 2.5, "E": 3.5, "A": 3.0, "N": 4.0}},
                    {"contact_id": 2, "ocean": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    return db, synthetic


def test_profile_columns_appear_only_with_a_mapping_and_missing_gets_the_fill(toy) -> None:
    db, _ = toy
    arena = load_arena("en", db)
    plain = FeatureTable(arena)
    with_profile = FeatureTable(arena, personality={1: PROFILE})
    with_midpoint = FeatureTable(arena, personality={1: PROFILE}, missing=MIDPOINT)
    idx = np.array([0, 1])
    c1, c4 = arena.customers[0], arena.customers[3]
    assert with_profile.rows_for(c1, idx).shape[1] == plain.rows_for(c1, idx).shape[1] + len(TRAITS)
    traits_c1 = with_profile.customer_vector(c1)[0][-len(TRAITS) :]
    assert np.allclose(traits_c1, [PROFILE[t] / 5.0 for t in TRAITS])
    assert np.isnan(with_profile.customer_vector(c4)[0][-len(TRAITS) :]).all()
    assert np.allclose(with_midpoint.customer_vector(c4)[0][-len(TRAITS) :], MIDPOINT)


def test_load_profiles_reads_the_database_and_the_snapshot(toy) -> None:
    db, synthetic = toy
    profiles = personality.load_profiles(db, synthetic)
    assert set(profiles["inferred"]) == {1, 2, 3} and profiles["inferred"][1] == PROFILE
    assert set(profiles["sampled"]) == {1, 4}  # 2 has no sampled profile


def test_paired_counts_discordant_pairs_and_refuses_misaligned_lists() -> None:
    first = [{"contact_id": i, "rank": r} for i, r in ((1, 1), (2, 20), (3, 5), (4, None))]
    second = [{"contact_id": i, "rank": r} for i, r in ((1, 3), (2, 2), (3, 30), (4, None))]
    stats = personality.paired(first, second)
    assert stats == {
        "n": 4,
        "hits_first": 2,
        "hits_second": 2,
        "difference": 0,
        "only_first": 1,
        "only_second": 1,
        "p_sign": 1.0,
    }
    subset = personality.paired(first, second, subset={1, 2})
    assert subset["n"] == 2 and subset["only_second"] == 1 and subset["difference"] == -1
    with pytest.raises(ValueError, match="aligned"):
        personality.paired(first, list(reversed(second)))


def test_run_writes_scores_pairs_tables_card_and_attachment(toy, tmp_path: Path) -> None:
    db, synthetic = toy
    run_dir = personality.run(
        arms=("svm_features",),
        langs=("en",),
        n_neg=3,
        db_path=db,
        synthetic_path=synthetic,
        base_dir=tmp_path / "runs",
        label="toy-personality",
        attachments_dir=tmp_path / "attachments",
    )
    assert sorted(p.name for p in (run_dir / "scores").glob("*.json")) == [
        "svm_features-inferred-en.json",
        "svm_features-none-en.json",
        "svm_features-sampled-en.json",
    ]
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert "3 of 4 customers" in config["variants"]["inferred"]
    assert "2 of 4 customers" in config["variants"]["sampled"]
    pairs = json.loads((run_dir / "pairs.json").read_text(encoding="utf-8"))
    assert len(pairs) == 2 * 3  # two protocols x three pairs
    by = {(p["protocol"], p["first"], p["second"]): p for p in pairs}
    assert by[("full", "inferred", "none")]["n"] == 4
    assert by[("full", "sampled", "none")]["n"] == 1  # customers with both profiles: contact 1 only
    card = (run_dir / "RESULTS.md").read_text(encoding="utf-8")
    assert "Model calls: none" in card and "sign test" in card
    assert (run_dir / "TABLE.md").exists() and (tmp_path / "runs" / "README.md").exists()
    rows = list(
        csv.DictReader(
            (tmp_path / "attachments" / "uc04-personality-feature.csv").open(encoding="utf-8")
        )
    )
    assert {r["kind"] for r in rows} == {"variant", "pair"}
    assert sum(1 for r in rows if r["kind"] == "variant") == 3 * 2
    md = (tmp_path / "attachments" / "uc04-personality-feature.md").read_text(encoding="utf-8")
    assert "Tabulka 1 –" in md and "Párové rozdíly" in md

    with pytest.raises(ValueError, match="feature arm"):
        personality.run(
            arms=("als_cf",), db_path=db, synthetic_path=synthetic, base_dir=tmp_path / "x"
        )
