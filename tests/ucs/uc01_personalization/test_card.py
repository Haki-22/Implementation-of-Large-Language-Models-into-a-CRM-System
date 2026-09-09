"""The UC-01 card and appendix files, built from a mock ladder run and a hand-made faithfulness folder."""

from __future__ import annotations

import csv
import json

import pytest

from ucs.uc01_personalization import card, data, levels, picker, runner
from utils.paths import SUBSTRATE_DB

pytestmark = pytest.mark.skipif(not SUBSTRATE_DB.exists(), reason="substrate.db not built")


def _pick():
    conn = data.connect()
    try:
        return picker.build_pick(conn, name="test-pick")
    finally:
        conn.close()


def test_card_finds_only_whole_ladder_runs_and_writes_card_and_attachments(tmp_path):
    pick = _pick()
    runs = tmp_path / "runs"
    picks = tmp_path / "picks"
    picks.mkdir()
    (picks / "test-pick.json").write_text(json.dumps(pick), encoding="utf-8")
    # a partial run (two levels) is not a ladder run of record
    runner.run(pick, levels_spec="0,2", provider="mock", runs_dir=runs, run_id="partial")
    assert card.ladder_runs(runs, allow_mock=True) == []
    full = runner.run(pick, levels_spec="all", provider="mock", runs_dir=runs, run_id="full")
    assert card.ladder_runs(runs, allow_mock=True) == [full]
    assert card.ladder_runs(runs) == []  # mock is never a record unless asked
    # a faithfulness folder as the command writes it (two contacts, one skipped)
    faith = runs / "faith"
    faith.mkdir()
    (faith / "faithfulness.json").write_text(
        json.dumps(
            [
                {"contact_id": 1, "responsiveness": 0.4, "ocean": {"O": 4}, "mirrored": {"O": 2}},
                {"contact_id": 2, "responsiveness": 0.6, "ocean": {"O": 3}, "mirrored": {"O": 3}},
                {"contact_id": 3, "skipped": "purchases"},
            ]
        ),
        encoding="utf-8",
    )
    (faith / "config.json").write_text(
        json.dumps(
            {
                "kind": "faithfulness",
                "pick": "test-pick",
                "provider": "mock",
                "model": "mock",
                "tier": None,
                "prompt_version": "t",
                "brief": 1,
                "calls": 4,
            }
        ),
        encoding="utf-8",
    )
    rec = card.records(runs, allow_mock=True)
    assert rec["ladder"] == full and rec["faithfulness"] == faith and rec["judges"] == []

    out = card.build(
        out_path=tmp_path / "RESULTS.md",
        runs_dir=runs,
        attachments_dir=tmp_path / "att",
        allow_mock=True,
    )
    text = out.read_text(encoding="utf-8")
    assert "## 1. The ladder — `runs/full/`" in text and "## 3. Faithfulness" in text
    assert "No judging of the ladder run yet" in text
    assert "mean responsiveness 0.500 over 2 contacts" in text
    rows = list(csv.DictReader((tmp_path / "att" / "uc01-ladder.csv").open(encoding="utf-8")))
    assert [r["level"] for r in rows] == list(levels.LADDER)
    assert all(r["run"] == "full" for r in rows)
    frows = list(
        csv.DictReader((tmp_path / "att" / "uc01-faithfulness.csv").open(encoding="utf-8"))
    )
    assert [r["contact_id"] for r in frows] == ["1", "2", "3"] and frows[2][
        "skipped"
    ] == "purchases"
    assert (tmp_path / "att" / "uc01-ladder.md").exists()
    with pytest.raises(FileNotFoundError):
        card.build(out_path=tmp_path / "x.md", runs_dir=tmp_path / "nothing", attachments_dir=None)
