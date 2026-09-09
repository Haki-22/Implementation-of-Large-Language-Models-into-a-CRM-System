"""OCEAN inference: targets by rule, schema-valid profiles only, a self-contained run folder, a guarded freeze.

Runs offline on a toy substrate with the mock provider (exempt from the model
switch). What must never go wrong: a target set is the union of rules with the
rules recorded, a contact without reviews is skipped and never called, a profile
outside 1-5 is a failed call, the run folder carries the resolved model and one
response file per call, and ``freeze`` refuses to silently drop reviewers the
snapshot holds today.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from ucs.uc01_personalization import ocean_inference as oi

# (contact, reviewer, group, number of reviews)
CONTACTS = [(1, "R1", "A", 3), (2, "R2", "B", 2), (3, "R3", "C", 0), (4, "R4", "A", 1)]


@pytest.fixture()
def toy_db(tmp_path: Path) -> Path:
    """A four-contact SQLite file (``CONTACTS``) with one review-less contact and one prospect."""
    path = tmp_path / "substrate.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE uc_contacts (id INTEGER PRIMARY KEY, reviewer_id TEXT, amazon_group TEXT);
        CREATE TABLE uc_reviews (id INTEGER PRIMARY KEY, contact_id INTEGER, rating REAL, helpful_up INTEGER,
                                 review_date TEXT, summary_en TEXT, text_en TEXT);
        """
    )
    conn.execute("INSERT INTO uc_contacts VALUES (99, NULL, NULL)")  # a prospect
    rid = 0
    for cid, reviewer, group, n_reviews in CONTACTS:
        conn.execute("INSERT INTO uc_contacts VALUES (?,?,?)", (cid, reviewer, group))
        for k in range(n_reviews):
            rid += 1
            conn.execute(
                "INSERT INTO uc_reviews VALUES (?,?,?,?,?,?,?)",
                (rid, cid, 5.0, 10 - k, f"2013-0{k + 1}-01", f"headline {k}", "x" * 1000),
            )
    conn.commit()
    conn.close()
    return path


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


PICK = {
    "name": "toy-pick",
    "contacts": {
        "2": {"tier": "full", "amazon_group": "B"},
        "99": {"tier": "prospect", "amazon_group": None},
    },
}
SAMPLE = {"name": "toy-sample", "contact_ids": [1, 2]}


def test_targets_are_the_union_of_rules_with_the_rules_recorded(toy_db: Path) -> None:
    targets, unmatched = oi.compose_targets(
        _conn(toy_db), pick=PICK, sample=SAMPLE, previous={"R3": {}, "R404": {}}, contacts=[4]
    )
    assert [t.contact_id for t in targets] == [1, 2, 3, 4]
    assert targets[0].sources == ("sample:toy-sample",)
    assert targets[1].sources == ("sample:toy-sample", "pick:toy-pick")
    assert targets[2].sources == ("previous",) and targets[3].sources == ("contacts",)
    assert unmatched == ["R404"]
    everyone, _ = oi.compose_targets(_conn(toy_db), everyone=True)
    assert [t.contact_id for t in everyone] == [1, 2, 3, 4]  # 99 has no reviewer
    with pytest.raises(LookupError):
        oi.compose_targets(_conn(toy_db), contacts=[500])


def test_review_block_caps_and_orders_by_helpfulness(toy_db: Path) -> None:
    block, used, total = oi.review_block(_conn(toy_db), 1)
    assert used == 3 and total == 3
    assert block.startswith("[*5.0] headline 0: ") and len(block.split("\n\n")) == 3
    assert all(
        len(line) <= len("[*5.0] headline 0: ") + oi.MAX_REVIEW_CHARS
        for line in block.split("\n\n")
    )


def test_validate_profile_rejects_what_the_schema_would_not(toy_db: Path) -> None:
    good = {"O": 3.456, "C": 3, "E": "4.1", "A": 5, "N": 1, "evidence_quotes": {"O": "q"}}
    profile = oi.validate_profile(good)
    assert profile["O"] == 3.46 and profile["E"] == 4.1
    assert profile["evidence_quotes"] == {"O": "q", "C": "", "E": "", "A": "", "N": ""}
    with pytest.raises(ValueError, match="outside"):
        oi.validate_profile({**good, "N": 5.5})
    with pytest.raises(ValueError, match="missing"):
        oi.validate_profile({k: v for k, v in good.items() if k != "A"})
    with pytest.raises(ValueError):
        oi.validate_profile(["not", "an", "object"])


def test_a_mock_run_writes_a_self_contained_folder(
    toy_db: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(oi.picker, "load_pick", lambda name: PICK)
    base = tmp_path / "runs"
    run_dir = oi.run(
        provider="mock",
        pick_name="toy-pick",
        contacts=[1, 3],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    assert run_dir.parent == base and run_dir.name.endswith(
        "ocean-inference-mock-mock-notier-3-contacts"
    )
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config["model"] == "mock" and config["tier"] is None
    assert config["prompt_version"] == oi.PROMPT_VERSION and config["targets"]["count"] == 3
    assert config["database"]["sha256"] and config["database"]["linked_contacts"] == 4
    assert (run_dir / "pick.json").exists() and (run_dir / "targets.json").exists()

    rows = list(csv.DictReader((run_dir / "status.csv").open(encoding="utf-8")))
    assert [(r["contact_id"], r["status"]) for r in rows] == [
        ("1", "ok"),
        ("2", "ok"),
        ("3", "skipped"),
    ]
    assert rows[2]["error"] == "no reviews" and rows[1]["sources"] == "pick:toy-pick"
    assert sorted(p.name for p in (run_dir / "responses").iterdir()) == ["R1.json", "R2.json"]
    response = json.loads((run_dir / "responses" / "R1.json").read_text(encoding="utf-8"))
    assert response["raw"]["O"] == 3.8 and response["profile"]["evidence_quotes"]["N"]
    assert response["prompt"].startswith("Customer ID: 1 (anonymized).")
    assert response["system_prompt"] == oi.SYSTEM_PROMPT and config["provider_cli_version"] is None

    profiles = json.loads((run_dir / "profiles.json").read_text(encoding="utf-8"))
    assert set(profiles) == {"R1", "R2"}
    assert profiles["R1"]["_run"] == run_dir.name and profiles["R1"]["_contact_id"] == 1
    assert profiles["R1"]["_reviews"] == 3 and profiles["R1"]["_reviews_used"] == 3
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["ok"] == 2 and summary["skipped"] == 1 and summary["failed"] == 0
    assert summary["by_group"] == {
        "A": {"targets": 1, "ok": 1},
        "B": {"targets": 1, "ok": 1},
        "C": {"targets": 1, "ok": 0},
    }
    card = (run_dir / "RESULTS.md").read_text(encoding="utf-8")
    assert "2 of 3 profiles" in card and "ocean_source = 'inferred'" in card


def test_limit_takes_the_first_targets_by_contact_id(toy_db: Path, tmp_path: Path) -> None:
    run_dir = oi.run(
        provider="mock",
        everyone=True,
        limit=2,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        snapshot=tmp_path / "none.json",
    )
    targets = json.loads((run_dir / "targets.json").read_text(encoding="utf-8"))
    assert [t["contact_id"] for t in targets] == [1, 2]


def test_an_out_of_range_answer_is_a_failed_call(toy_db: Path, tmp_path: Path, monkeypatch) -> None:
    async def bad(*args, **kwargs):
        return {"O": 9, "C": 3, "E": 3, "A": 3, "N": 3, "evidence_quotes": {}}

    monkeypatch.setattr(oi, "generate_json", bad)
    run_dir = oi.run(
        provider="mock",
        contacts=[1],
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        snapshot=tmp_path / "none.json",
    )
    rows = list(csv.DictReader((run_dir / "status.csv").open(encoding="utf-8")))
    assert rows[0]["status"] == "failed" and "outside" in rows[0]["error"]
    assert json.loads((run_dir / "profiles.json").read_text(encoding="utf-8")) == {}


def test_freeze_merges_runs_and_guards_the_snapshot(toy_db: Path, tmp_path: Path) -> None:
    base = tmp_path / "runs"
    first = oi.run(
        provider="mock",
        contacts=[1],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    second = oi.run(
        provider="mock",
        contacts=[2],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    output = tmp_path / "ocean_inferred.json"
    path, counts = oi.freeze([first, second], output=output)
    frozen = json.loads(path.read_text(encoding="utf-8"))
    assert list(frozen) == ["R1", "R2"] and counts == {"profiles": 2, "dropped": 0, "runs": 2}
    assert frozen["R2"]["_run"] == second.name and set("OCEAN") <= set(frozen["R1"])

    with pytest.raises(ValueError, match="both"):
        oi.freeze([first, first], output=tmp_path / "other.json")
    with pytest.raises(FileExistsError, match="R2"):
        oi.freeze([first], output=output)
    _, counts = oi.freeze([first], output=output, replace=True)
    assert counts["dropped"] == 1 and list(json.loads(output.read_text(encoding="utf-8"))) == ["R1"]


def test_previous_carries_today_s_reviewers_over(toy_db: Path, tmp_path: Path) -> None:
    snapshot = tmp_path / "ocean_inferred.json"
    snapshot.write_text(
        json.dumps({"R2": {"O": 3, "C": 3, "E": 3, "A": 3, "N": 3}, "R404": {}}), encoding="utf-8"
    )
    run_dir = oi.run(
        provider="mock",
        previous=True,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        snapshot=snapshot,
    )
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config["targets"]["count"] == 1 and config["targets"]["unmatched_previous"] == ["R404"]
    assert config["targets"]["previous"] == "ocean_inferred.json (2 profiles)"


def test_exclude_runs_continues_a_batch_where_the_last_one_stopped(
    toy_db: Path, tmp_path: Path
) -> None:
    base = tmp_path / "runs"
    first = oi.run(
        provider="mock",
        contacts=[1, 2],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    second = oi.run(
        provider="mock",
        everyone=True,
        exclude_runs=[first],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    targets = json.loads((second / "targets.json").read_text(encoding="utf-8"))
    assert [t["contact_id"] for t in targets] == [3, 4]
    config = json.loads((second / "config.json").read_text(encoding="utf-8"))
    assert (
        config["targets"]["exclude_runs"] == [first.name]
        and config["targets"]["excluded_count"] == 2
    )
    with pytest.raises(LookupError, match="already"):
        oi.run(
            provider="mock",
            contacts=[1],
            exclude_runs=[first],
            db_path=toy_db,
            base_dir=base,
            snapshot=tmp_path / "none.json",
        )


def test_attachment_is_generated_from_the_run_folders_the_snapshot_names(
    toy_db: Path, tmp_path: Path
) -> None:
    base = tmp_path / "runs"
    first = oi.run(
        provider="mock",
        contacts=[1],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    second = oi.run(
        provider="mock",
        contacts=[2],
        db_path=toy_db,
        base_dir=base,
        snapshot=tmp_path / "none.json",
    )
    snapshot = tmp_path / "ocean_inferred.json"
    oi.freeze([first, second], output=snapshot)
    may = tmp_path / "may.json"
    may.write_text(
        json.dumps({"R1": {"O": 4.0, "C": 3.6, "E": 3.2, "A": 3.7, "N": 2.9}}), encoding="utf-8"
    )
    written = oi.attachment_build(
        snapshot=snapshot, base=base, out_dir=tmp_path / "att", may_record=may
    )
    assert [p.name for p in written] == ["ocean-inference.csv", "ocean-inference.md"]
    rows = list(csv.DictReader(written[0].open(encoding="utf-8")))
    tables = {r["table"] for r in rows}
    assert {f"run:{first.name}", f"run:{second.name}", "profiles", "may_2026"} <= tables
    by_key = {(r["table"], r["key"]): r["value"] for r in rows}
    assert by_key[("profiles", "all:n")] == "2" and by_key[("profiles", "A:O")] == "3.80 ± 0.00"
    assert by_key[("may_2026", "overlap")] == "1" and by_key[("may_2026", "O:mean_diff")] == "-0.2"
    md = written[1].read_text(encoding="utf-8")
    assert "Tabulka 3 – Rysy BFI-2 po skupinách" in md and first.name in md and "Tabulka 4" in md
