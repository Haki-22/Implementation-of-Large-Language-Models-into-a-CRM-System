"""generate(), the picker and the runner against the built substrate database (mock provider, no spend).

Skipped when ``substrate.db`` has not been built.
"""

from __future__ import annotations

import csv
import json

import pytest

from ucs.uc01_personalization import data, picker, prompts, runner
from ucs.uc01_personalization.generate import generate_sync
from utils.paths import SUBSTRATE_DB

pytestmark = pytest.mark.skipif(not SUBSTRATE_DB.exists(), reason="substrate.db not built")


def _pick():
    conn = data.connect()
    try:
        return picker.build_pick(conn, name="test-pick")
    finally:
        conn.close()


def _first(pick, tier):
    return next(int(i) for i, f in pick["contacts"].items() if f["tier"] == tier)


def test_no_model_levels_need_no_switch_and_pass_the_rules():
    pick = _pick()
    cid = _first(pick, "linked")
    brief = pick["briefs"][0]
    g0 = generate_sync(cid, brief, "0")
    g1 = generate_sync(cid, brief, "1")
    assert not g0.used_model and not g1.used_model
    assert g0.rules["accepted"] is False and "VOCATIVE_MISMATCH" in g0.rules["failures"]
    assert g1.rules["accepted"] is True and g1.rules["unchecked"] == []
    # The stored greeting is the whole salutation; the neutral fallback of the two
    # foreign-name contacts ("Dobrý den,") already carries its comma.
    greeting = pick["contacts"][str(cid)]["name_vocative"].rstrip(",")
    assert g1.text.startswith(greeting + ",")


def test_model_level_with_mock_carries_only_its_slots_and_is_judged():
    pick = _pick()
    cid = _first(pick, "linked")
    g = generate_sync(cid, pick["briefs"][0], "3a", provider="mock")
    assert g.used_model and g.ok and g.rules is not None
    assert "Častá slova zákazníka" in g.user_prompt and "Poslední nákupy" not in g.user_prompt
    assert g.slots == ["frequent_words", "style_excerpt"]
    assert g.prompt_version and g.provider == "mock"


def test_prospect_is_skipped_on_behaviour_levels_not_called():
    pick = _pick()
    prospect = _first(pick, "prospect")
    g = generate_sync(prospect, pick["briefs"][0], "3b", provider="mock")
    assert g.skipped == ["purchases"] and g.text is None and not g.ok
    assert generate_sync(prospect, pick["briefs"][0], "2", provider="mock").ok


def test_linked_contact_runs_the_behaviour_rung_and_the_top_rung_waits_only_for_uc04():
    pick = _pick()
    linked = _first(pick, "linked")
    assert generate_sync(linked, pick["briefs"][0], "3", provider="mock").ok
    # Every linked contact has Czech text, purchases, an inferred profile, topics and a
    # lifecycle stage; only UC-04's recommendations arrive with the `for-uc01` run.
    six = generate_sync(linked, pick["briefs"][0], "6", provider="mock")
    assert set(six.skipped) <= {"recommendations"}
    facts = pick["contacts"][str(linked)]
    assert facts["has_uc04"] == (not six.skipped)


def test_defective_row_runs_every_level_and_the_judge_skips_what_is_not_stored():
    pick = _pick()
    defective = pick["strata"]["defective"][0]
    facts = pick["contacts"][str(defective)]
    assert facts["tier"] == "defective" and facts["name_vocative"] is None
    g1 = generate_sync(defective, pick["briefs"][0], "1")
    assert g1.ok and g1.text.startswith(("Dobrý den,", "Ahoj "))
    assert "vocative" in g1.rules["unchecked"] and g1.rules["accepted"]
    g2 = generate_sync(defective, pick["briefs"][0], "2", provider="mock")
    assert g2.ok and g2.skipped == [] and "Oslovení: není uloženo" in g2.user_prompt
    assert facts["name"] in g2.user_prompt


def test_pick_mixes_the_tiers_per_cell_and_is_deterministic():
    a, b = _pick(), _pick()
    assert a["cells"] == b["cells"] and a["strata"] == b["strata"] and a["briefs"] == b["briefs"]
    assert len(a["reading_set"]) == 16 and len(set(a["reading_set"])) == 16
    assert a["tier_mix"] == ["linked", "linked", "linked", "prospect"]
    for cell, ids in a["cells"].items():
        assert [a["contacts"][str(i)]["tier"] for i in ids] == a["tier_mix"], cell
        formality, gender = cell.split("_")
        for i in ids:
            f = a["contacts"][str(i)]
            assert f["is_clean"] and f["gender"] == gender
            assert f["formal"] == (formality == "formal")
    for i in a["reading_set"]:
        f = a["contacts"][str(i)]
        if f["tier"] == "linked":
            assert f["orders"] > 0 and f["has_czech"] and f["ocean_source"]
        else:
            assert f["tier"] == "prospect" and f["orders"] == 0
    assert all(not a["contacts"][str(c)]["is_clean"] for c in a["strata"]["defective"])
    assert a["pools"]["linked"] > 0 and a["core_size"] == a["pools"]["linked"]
    assert a["brief_titles"] == {
        str(b): t for b, t in zip(a["briefs"], picker.LADDER_BRIEFS.values(), strict=True)
    }


def test_runner_writes_a_self_contained_run_folder(tmp_path):
    pick = _pick()
    folder = runner.run(
        pick,
        levels_spec="0,1,2,3b",
        provider="mock",
        judges=("rules",),
        runs_dir=tmp_path,
        run_id="t",
    )
    assert {p.name for p in folder.iterdir()} == {
        "config.json",
        "pick.json",
        "messages.jsonl",
        "results.csv",
        "summary.json",
    }
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    assert config["levels"] == ["0", "1", "2", "3b"] and config["provider"] == "mock"
    rows = list(csv.DictReader((folder / "results.csv").open(encoding="utf-8")))
    n_contacts = len(pick["reading_set"]) + len(pick["strata"]["defective"])
    n_briefs = len(pick["briefs"])
    # L0, L1, L2 run on all three briefs; the 3b arm on the upsell brief only
    assert len(rows) == n_contacts * (n_briefs * 3 + 1)
    assert config["briefs_by_level"]["3b"] == [pick["briefs"][1]]
    assert {r["stratum"] for r in rows} == {"linked", "prospect", "defective"}
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["1"]["rules_rate"] == 1.0
    # L0 fails the greeting for every contact that has one stored; the defective rows are unchecked
    assert (
        summary["0"]["rules_failures"]["VOCATIVE_MISMATCH"] == len(pick["reading_set"]) * n_briefs
    )
    assert (
        summary["0"]["rules_unchecked"]["vocative"] == len(pick["strata"]["defective"]) * n_briefs
    )
    assert "purchases" in summary["3b"]["skipped"]  # the prospects
    with pytest.raises(FileExistsError):
        runner.run(pick, levels_spec="0", provider="mock", runs_dir=tmp_path, run_id="t")


# ---------------------------------------------------------------------------
# Provenance: a row and a run record the model that ran, not the argument
# ---------------------------------------------------------------------------


def test_generation_records_resolved_model_not_argument(monkeypatch, tmp_path):
    """A default run must be self-describing: model "gpt-5.5", never null."""
    from utils import llm_switch
    from utils.generation import DEFAULT_MODELS

    pick = _pick()
    cid = _first(pick, "linked")
    mock = generate_sync(cid, pick["briefs"][0], "2", provider="mock")
    assert (mock.provider, mock.model, mock.tier) == ("mock", "mock", None)
    assert (
        generate_sync(cid, pick["briefs"][0], "1", provider="mock").model is None
    )  # no model at L1

    # switch off: the adapter refuses before any subprocess, the row still names the model
    monkeypatch.delenv("THESIS_LLM_CALLS", raising=False)
    monkeypatch.setattr(llm_switch, "DOTENV_PATH", tmp_path / "no.env")
    off = generate_sync(cid, pick["briefs"][0], "2", provider="codex")
    assert off.model == DEFAULT_MODELS["codex"] and off.tier == "low"
    assert off.error and off.error.startswith("LLMCallsDisabledError")
    alias = generate_sync(cid, pick["briefs"][0], "2", provider="claude", model="sonnet")
    assert alias.model.startswith("claude-sonnet-")

    # a model outside the generated menu is an error row, not a crash, and no call is made
    bad = generate_sync(cid, pick["briefs"][0], "2", provider="codex", model="gpt-3")
    assert bad.error and bad.error.startswith("ValueError") and bad.text is None


def test_run_config_records_resolved_model(tmp_path):
    folder = runner.run(_pick(), levels_spec="2", provider="mock", runs_dir=tmp_path, run_id="t2")
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    assert config["model"] == "mock" and config["tier"] is None
    assert config["requested"] == {"model": None, "tier": "low"}


# ---------------------------------------------------------------------------
# Briefs per level (D-UC01-3): tiers on every brief, each arm on one
# ---------------------------------------------------------------------------


def test_pick_maps_every_level_to_its_briefs():
    from ucs.uc01_personalization import levels

    pick = _pick()
    by_level = pick["briefs_by_level"]
    assert set(by_level) == set(levels.LADDER)
    inv, up, follow = pick["briefs"]
    for tier in ("0", "1", "2", "3", "5", "6"):
        assert by_level[tier] == [inv, up, follow], tier
    assert by_level["3a"] == [inv] and by_level["3d"] == [inv]
    for arm in ("3b", "3c", "4", "6a", "6b"):
        assert by_level[arm] == [up], arm
    assert by_level["6c"] == [follow]
    with pytest.raises(LookupError):
        picker.briefs_by_level([1, 2])  # one id per category, no more, no less


def test_runner_follows_the_map_unless_briefs_are_given(tmp_path):
    pick = _pick()
    n_contacts = len(pick["reading_set"]) + len(pick["strata"]["defective"])
    folder = runner.run(pick, levels_spec="2,6c", provider="mock", runs_dir=tmp_path, run_id="m")
    rows = list(csv.DictReader((folder / "results.csv").open(encoding="utf-8")))
    assert sum(r["level"] == "2" for r in rows) == n_contacts * 3
    assert sum(r["level"] == "6c" for r in rows) == n_contacts  # follow-up brief only
    assert {r["brief_id"] for r in rows if r["level"] == "6c"} == {str(pick["briefs"][2])}
    forced = runner.run(
        pick,
        levels_spec="2,6c",
        briefs=[pick["briefs"][0]],
        provider="mock",
        runs_dir=tmp_path,
        run_id="f",
    )
    forced_rows = list(csv.DictReader((forced / "results.csv").open(encoding="utf-8")))
    assert len(forced_rows) == n_contacts * 2 and {r["brief_id"] for r in forced_rows} == {
        str(pick["briefs"][0])
    }


def test_run_reuses_identical_calls_of_an_earlier_folder_and_nothing_after_a_prompt_change(
    tmp_path, monkeypatch
):
    pick = _pick()
    one = [pick["reading_set"][0]]
    a = runner.run(
        pick, levels_spec="2", provider="mock", runs_dir=tmp_path, run_id="a", contacts=one
    )
    b = runner.run(
        pick,
        levels_spec="2",
        provider="mock",
        runs_dir=tmp_path,
        run_id="b",
        contacts=one,
        reuse=["a"],
    )
    rows_a = [json.loads(line) for line in (a / "messages.jsonl").open(encoding="utf-8")]
    rows_b = [json.loads(line) for line in (b / "messages.jsonl").open(encoding="utf-8")]
    assert rows_b and all(r["reused_from"] == "a" for r in rows_b if r["used_model"])
    assert [r["text"] for r in rows_b] == [r["text"] for r in rows_a]
    assert all(r["rules"] is not None for r in rows_b)  # the rules judge ran afresh
    config = json.loads((b / "config.json").read_text(encoding="utf-8"))
    summary = json.loads((b / "summary.json").read_text(encoding="utf-8"))
    assert config["reuse"] == ["a"] and config["reused"] == len(rows_b)
    assert summary["2"]["reused"] == summary["2"]["generated"]
    rows = list(csv.DictReader((b / "results.csv").open(encoding="utf-8")))
    assert {r["reused_from"] for r in rows} == {"a"}
    # a different prompt version makes every stored row a stranger: nothing is copied
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "0.0.0-test")
    c = runner.run(
        pick,
        levels_spec="2",
        provider="mock",
        runs_dir=tmp_path,
        run_id="c",
        contacts=one,
        reuse=["a"],
    )
    rows_c = [json.loads(line) for line in (c / "messages.jsonl").open(encoding="utf-8")]
    assert all(r["reused_from"] is None for r in rows_c)
    with pytest.raises(FileNotFoundError):
        runner.run(
            pick, levels_spec="2", provider="mock", runs_dir=tmp_path, run_id="d", reuse=["nope"]
        )
