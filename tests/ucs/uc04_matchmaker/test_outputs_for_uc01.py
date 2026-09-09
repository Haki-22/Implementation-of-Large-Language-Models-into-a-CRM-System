"""UC-04 outputs for UC-01: the population rule, grounded reasons, verbatim aspect quotes, topics, the handoff and the freeze.

Runs offline on a toy substrate with the mock provider. What must never go wrong: prose
only for the pick's linked contacts and classical fields for everyone; a reason citing a
purchase id outside the history is a failed call; an aspect quote that is not verbatim
is marked not grounded; the handoff has the shape the database build reads; ``freeze``
refuses to overwrite the file of record without ``--replace``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ucs.uc04_matchmaker.data import load_arena
from ucs.uc04_matchmaker.outputs_for_uc01 import aspects, handoff, inputs, reasons, topics
from ucs.uc04_matchmaker.outputs_for_uc01 import run as outputs_run

PRODUCTS = [
    ("P1", "Cable", "Kabel USB", "Accessories"),
    ("P2", "Mouse", "Myš bezdrátová", "Computers"),
    ("P3", "Keyboard", "Klávesnice", "Computers"),
    ("P4", "Monitor", None, "Displays"),
    ("P5", "Headset", "Sluchátka", "Audio"),
    ("P6", "Webcam", "Webkamera", "Computers"),
    ("P7", "Speaker", "Reproduktor", "Audio"),
    ("P8", "Charger", "Nabíječka", "Accessories"),
]
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
            ("P5", 5, "2013-03-06"),
        ],
    ),
    (3, "B", [("P2", 5, "2013-01-10"), ("P3", 4, "2013-02-10"), ("P6", 2, "2013-05-10")]),
    (4, "C", [("P1", 3, "2013-01-15"), ("P4", 4, "2013-02-15"), ("P7", 4, "2013-03-15")]),
]


@pytest.fixture()
def toy_db(tmp_path: Path) -> Path:
    """A four-customer, eight-product SQLite file (``CUSTOMERS``/``PRODUCTS``) under ``tmp_path``."""
    path = tmp_path / "substrate.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE uc_contacts (id INTEGER PRIMARY KEY, reviewer_id TEXT, amazon_group TEXT, lifecycle_stage TEXT);
        CREATE TABLE uc_lifecycle_stages (code TEXT PRIMARY KEY, label_cs TEXT);
        CREATE TABLE uc_products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, name_cs TEXT, category TEXT, description TEXT, price REAL);
        CREATE TABLE uc_reviews (id INTEGER PRIMARY KEY, contact_id INTEGER, product_id INTEGER, rating REAL,
                                 review_date TEXT, summary_en TEXT, text_en TEXT, summary_cs TEXT, text_cs TEXT);
        INSERT INTO uc_lifecycle_stages VALUES ('active', 'aktivní zákazník');
        """
    )
    for i, (sku, name, name_cs, cat) in enumerate(PRODUCTS, start=1):
        conn.execute(
            "INSERT INTO uc_products VALUES (?,?,?,?,?,?,?)",
            (i, sku, name, name_cs, cat, f"A {name.lower()}", 9.9),
        )
    conn.execute("INSERT INTO uc_contacts VALUES (99, NULL, NULL, 'prospect')")
    rid = 0
    for cid, group, reviews in CUSTOMERS:
        conn.execute("INSERT INTO uc_contacts VALUES (?,?,?,?)", (cid, f"R{cid}", group, "active"))
        for sku, rating, day in reviews:
            rid += 1
            text_cs = (
                f"Recenze {sku} kontakt {cid}: funguje dobře a zvuk je čistý." if cid != 3 else None
            )
            conn.execute(
                "INSERT INTO uc_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    cid,
                    PRODUCTS.index(next(p for p in PRODUCTS if p[0] == sku)) + 1,
                    rating,
                    day,
                    "ok",
                    "english",
                    "ok cs",
                    text_cs,
                ),
            )
    conn.commit()
    conn.close()
    return path


PICK = {
    "name": "toy-pick",
    "contacts": {
        "2": {"tier": "full", "amazon_group": "A"},
        "4": {"tier": "defective", "amazon_group": "C"},
        "99": {"tier": "prospect", "amazon_group": None},
    },
}


def test_prose_population_is_the_picks_linked_contacts() -> None:
    assert outputs_run.prose_contacts(PICK) == [2, 4]


def test_no_hold_out_arena_keeps_every_purchase(toy_db: Path) -> None:
    arena = load_arena("en", toy_db, hold_out=False)
    c1 = arena.customers[0]
    assert len(c1.history) == 4 and c1.held_out.asin == "P4" and "P4" in c1.history_asins
    lines, id_to_asin = inputs.history_lines(c1, arena.catalog)
    assert lines[0].startswith("H01 2013-04-01 ★3 Monitor") and id_to_asin["H04"] == "P1"
    assert lines[3].endswith("Kabel USB")  # Czech title where the catalogue has one


def test_reason_validation_rejects_unknown_evidence_and_long_sentences() -> None:
    id_to_asin = {"H01": "P1", "H02": "P2"}
    ok = reasons.validate_reason({"reason": "Doplní kabel.", "evidence_ids": ["H01"]}, id_to_asin)
    assert ok == {"reason": "Doplní kabel.", "evidence_ids": ["H01"]}
    with pytest.raises(ValueError, match="not in the history"):
        reasons.validate_reason({"reason": "x", "evidence_ids": ["H07"]}, id_to_asin)
    with pytest.raises(ValueError, match="words"):
        reasons.validate_reason({"reason": "slovo " * 40, "evidence_ids": ["H01"]}, id_to_asin)


def test_reason_validation_rejects_ids_in_the_sentence_and_json() -> None:
    id_to_asin = {"H01": "P1", "H02": "P2"}
    with pytest.raises(ValueError, match="names purchase ids"):
        reasons.validate_reason(
            {"reason": "Doplní kabel (H01, H02).", "evidence_ids": ["H01"]}, id_to_asin
        )
    with pytest.raises(ValueError, match="JSON"):
        reasons.validate_reason(
            {"reason": '{"reason": "x", "evidence_ids": ["H01"]}', "evidence_ids": ["H01"]},
            id_to_asin,
        )


def test_persona_label_is_a_slug() -> None:
    from ucs.uc04_matchmaker.outputs_for_uc01.persona import slug

    assert slug("věrný-počítač-sbírač") == "verny_pocitac_sbirac"
    assert (
        slug("Apple Ecosystem Loyalist!") == "apple_ecosystem_loyalist" and slug("---") == "persona"
    )


def test_aspect_quote_must_be_verbatim() -> None:
    text = "Sluchátka: Zvuk je čistý a basy   hluboké.\nMyš: baterie vydrží týden."
    assert aspects.quote_found("zvuk je čistý a basy hluboké", text)
    assert aspects.quote_found("„Baterie vydrží týden.“", text)
    assert not aspects.quote_found("zvuk je výborný", text)
    assert aspects.quote_found('zvuk je "čistý" a basy hluboké', "Zvuk je „čistý“ a basy hluboké.")
    assert not aspects.quote_found("", text)


def test_topics_over_a_toy_catalogue(toy_db: Path) -> None:
    arena = load_arena("en", toy_db, hold_out=False)
    doc_topic, labels = topics.fit(arena)
    per = topics.per_customer(arena, doc_topic, labels)
    assert set(per) == {1, 2, 3, 4} and all(per[c] for c in per)
    assert all(t["_paradigm"] == "lda" and t["evidence_titles"] for t in per[1])


def test_run_writes_the_folder_the_handoff_and_the_attachment(
    toy_db: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(outputs_run.picker, "load_pick", lambda name: PICK)
    run_dir = outputs_run.run(
        provider="mock",
        pick_name="toy-pick",
        top_k=2,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        attachments_dir=tmp_path / "att",
        label="toy-outputs",
    )
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "RESULTS.md",
        "calls",
        "config.json",
        "handoff.json",
        "pick.json",
        "summary.json",
        "topics.json",
    ]
    calls = sorted(
        str(p.relative_to(run_dir / "calls")) for p in (run_dir / "calls").rglob("*.json")
    )
    assert calls == [
        "aspects/2.json",
        "aspects/4.json",
        "persona/2.json",
        "persona/4.json",
        "reasons/2-1.json",
        "reasons/2-2.json",
        "reasons/4-1.json",
        "reasons/4-2.json",
    ]
    call = json.loads((run_dir / "calls" / "reasons" / "2-1.json").read_text(encoding="utf-8"))
    assert (
        call["prompt"].startswith("Zákazník Z-2")
        and call["system_prompt"]
        and call["status"] == "ok"
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))["counts"]
    assert summary == {
        "prose_contacts": 2,
        "reasons_ok": 4,
        "reasons_failed": 0,
        "reasons_grounded": 4,
        "personas_ok": 2,
        "personas_failed": 0,
        "aspects_contacts_ok": 2,
        "aspects_contacts_failed": 0,
        "aspects_contacts_skipped": 0,
        "aspects_total": 2,
        "aspects_grounded": 2,
        "topics_contacts": 4,
        "calls": 8,
    }
    payload = json.loads((run_dir / "handoff.json").read_text(encoding="utf-8"))
    assert payload["_meta"]["schema"] == handoff.SCHEMA and set(payload["users"]) == {
        "R1",
        "R2",
        "R3",
        "R4",
    }
    u2 = payload["users"]["R2"]
    assert len(u2["topk_recommendations"]) == 2 and u2["topk_recommendations"][0]["grounded"]
    assert u2["persona"]["price_segment"] == "mid" and u2["lifecycle"] == {
        "stage": "active",
        "label_cs": "aktivní zákazník",
    }
    assert u2["absa"]["aspects"][0]["grounded"] is True
    assert (
        payload["users"]["R1"]["topk_recommendations"] == []
        and payload["users"]["R1"]["topic_clusters"]
    )
    card = (run_dir / "RESULTS.md").read_text(encoding="utf-8")
    assert "4 of 4 sentences" in card and "2 of 2 quotes found verbatim" in card
    assert (tmp_path / "att" / "uc04-outputs-for-uc01.md").exists() and (
        tmp_path / "runs" / "README.md"
    ).exists()

    smoke = outputs_run.run(
        provider="mock",
        pick_name="toy-pick",
        limit=1,
        top_k=1,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        attachments_dir=tmp_path / "att2",
        label="toy-smoke",
    )
    assert not (tmp_path / "att2").exists()  # a smoke keeps its card, never the appendix
    assert json.loads((smoke / "summary.json").read_text(encoding="utf-8"))["counts"]["calls"] == 3

    output = tmp_path / "record" / "uc04_to_uc01_handoff.json"
    path, meta = handoff.freeze(run_dir, output=output)
    assert path == output and meta["run"] == run_dir.name
    with pytest.raises(FileExistsError, match="replace"):
        handoff.freeze(run_dir, output=output)
    handoff.freeze(run_dir, output=output, replace=True)


def test_aspects_skip_a_contact_without_czech_reviews(toy_db: Path, tmp_path: Path) -> None:
    import asyncio

    from ucs.uc04_matchmaker.data import connect
    from ucs.uc04_matchmaker.outputs_for_uc01.calls import Provider

    conn = connect(toy_db)
    try:
        out = asyncio.run(
            aspects.generate(
                conn,
                [3],
                provider=Provider("mock", None, None, "mock", None),
                run_dir=tmp_path / "r",
                concurrency=2,
            )
        )
    finally:
        conn.close()
    assert out[3]["status"] == "skipped" and out[3]["aspects"] == []
