"""The model-judge cascade (D-UC01-5): span check, verdict status, routing table, second pass."""

from __future__ import annotations

import json

import pytest

from ucs.uc01_personalization import judge, judge_run, picker, runner
from ucs.uc01_personalization import data as data_mod
from ucs.uc01_personalization.judge import (
    FINAL_HUMAN,
    FINAL_PARTIAL,
    FINAL_VALID,
    Cascade,
    JudgeSpec,
    JudgeVerdict,
    RulesVerdict,
    decide,
    default_cascade,
    evaluate_judge_json,
    judge_cascade,
    span_status,
)

from utils.paths import SUBSTRATE_DB

# The five tests below read the real substrate database; on a fresh clone it does not
# exist until the data setup has run, so they skip instead of failing.
needs_db = pytest.mark.skipif(
    not SUBSTRATE_DB.exists(),
    reason="substrate.db not built; run: python -m substrate.pipeline.build_all --force --from database",
)

MSG = "Vážená paní Nováková,\n\nvěříme, že jste byla spokojena. Neváhejte nás kontaktovat."


def _json(
    v_ok=True,
    r_ok=True,
    g_ok=True,
    v="Vážená paní Nováková,",
    r="Neváhejte",
    g="jste byla spokojena",
    reason=None,
):
    d = {
        "vocative_ok": v_ok,
        "vocative_evidence": v,
        "register_ok": r_ok,
        "register_evidence": r,
        "gender_ok": g_ok,
        "gender_evidence": g,
    }
    if reason is not None:
        d["reason"] = reason
    return d


def _verdict(status="FULL", ok=True, role="judge", provider="claude"):
    """A ready-made JudgeVerdict for the routing tests."""
    if status == "MALFORMED":
        return JudgeVerdict(role=role, provider=provider, model="m", tier="low", error="timeout")
    spans = {c: "found" for c in judge.CRITERIA}
    if status == "PARTIAL":
        spans["gender"] = "missing"
    return JudgeVerdict(
        role=role,
        provider=provider,
        model="m",
        tier="low",
        ok={c: ok for c in judge.CRITERIA},
        evidence={c: "x" for c in judge.CRITERIA},
        spans=spans,
        status=status,
    )


RULES_OK = RulesVerdict(True, True, False)
RULES_FAIL = RulesVerdict(False, True, False)


# ---------------------------------------------------------------------------
# The span check and the verdict status
# ---------------------------------------------------------------------------


def test_span_status_labels():
    assert span_status("jste byla spokojena", MSG) == "found"
    assert span_status("JSTE  byla\nspokojena", MSG) == "found"  # case and whitespace
    assert span_status("„Neváhejte“", MSG) == "found"  # quotes stripped
    assert span_status("jste byl spokojen", MSG) == "missing"
    assert span_status("neposuzováno", MSG) == "n/a"
    assert span_status("", MSG) == "missing"
    assert span_status(None, MSG) == "missing"


def test_evaluate_judge_json_status_and_verdict():
    full = evaluate_judge_json(_json(), MSG, role="judge", provider="claude", model="m", tier="low")
    assert full.status == "FULL" and full.verdict == "valid" and full.spans["gender"] == "found"
    partial = evaluate_judge_json(
        _json(g="jste byl spokojen"), MSG, role="judge", provider="claude", model="m", tier="low"
    )
    assert partial.status == "PARTIAL" and partial.verdict == "valid"  # the boolean is kept
    invalid = evaluate_judge_json(
        _json(g_ok=False), MSG, role="judge", provider="claude", model="m", tier="low"
    )
    assert invalid.status == "FULL" and invalid.verdict == "invalid"
    bad = evaluate_judge_json(
        {"vocative_ok": "yes"}, MSG, role="judge", provider="claude", model="m", tier="low"
    )
    assert bad.status == "MALFORMED" and bad.verdict is None and bad.error
    arb = evaluate_judge_json(
        _json(reason="ok"), MSG, role="arbiter", provider="codex", model="m", tier="high"
    )
    assert arb.reason == "ok"


# ---------------------------------------------------------------------------
# The routing table
# ---------------------------------------------------------------------------


def test_rules_failure_goes_to_the_human_without_a_call():
    assert decide(3, RULES_FAIL, [], None) == (FINAL_HUMAN, "rules:VOCATIVE_MISMATCH")


@pytest.mark.parametrize(
    ("status", "ok", "expected"),
    [
        ("FULL", True, (FINAL_VALID, "judge_valid")),
        ("FULL", False, (FINAL_HUMAN, "judge_invalid")),
        ("PARTIAL", True, (FINAL_PARTIAL, "judge_partial_evidence")),
        ("MALFORMED", True, (FINAL_HUMAN, "judge_malformed")),
    ],
)
def test_level_1_routing(status, ok, expected):
    assert decide(1, RULES_OK, [_verdict(status, ok)], None) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (("FULL", True), ("FULL", True), (FINAL_VALID, "judges_agree_valid")),
        (("FULL", False), ("FULL", False), (FINAL_HUMAN, "judges_agree_invalid")),
        (("FULL", True), ("FULL", False), (FINAL_HUMAN, "judges_disagree")),
        (("FULL", True), ("PARTIAL", True), (FINAL_PARTIAL, "judge_partial_evidence")),
        (("PARTIAL", True), ("PARTIAL", True), (FINAL_PARTIAL, "judge_partial_evidence")),
        (("FULL", True), ("MALFORMED", True), (FINAL_HUMAN, "judge_malformed")),
    ],
)
def test_level_2_routing(a, b, expected):
    judges = [_verdict(*a, provider="claude"), _verdict(*b, provider="agy")]
    assert decide(2, RULES_OK, judges, None) == expected


def test_level_3_routing_hands_every_non_composed_pair_to_the_arbiter():
    agree = [_verdict("FULL", True, provider="claude"), _verdict("FULL", True, provider="agy")]
    assert decide(3, RULES_OK, agree, None) == (FINAL_VALID, "judges_agree_valid")
    onward = [_verdict("FULL", True, provider="claude"), _verdict("PARTIAL", True, provider="agy")]
    assert decide(3, RULES_OK, onward, _verdict("FULL", True, role="arbiter")) == (
        FINAL_VALID,
        "arbiter_valid",
    )
    assert decide(3, RULES_OK, onward, _verdict("FULL", False, role="arbiter")) == (
        FINAL_HUMAN,
        "arbiter_invalid",
    )
    assert decide(3, RULES_OK, onward, _verdict("PARTIAL", True, role="arbiter")) == (
        FINAL_PARTIAL,
        "arbiter_partial_evidence",
    )
    assert decide(3, RULES_OK, onward, _verdict("MALFORMED", True, role="arbiter")) == (
        FINAL_HUMAN,
        "arbiter_malformed",
    )


# ---------------------------------------------------------------------------
# Cascade configuration
# ---------------------------------------------------------------------------


def test_default_cascade_follows_the_writer():
    c = default_cascade(3, "codex")
    assert [j.provider for j in c.judges] == ["claude", "agy"] and c.arbiter == JudgeSpec(
        "codex", None, "high"
    )
    assert [j.provider for j in default_cascade(2, "claude").judges] == ["agy", "codex"]
    assert [j.provider for j in default_cascade(1, "agy").judges] == ["claude"]
    assert default_cascade(2, "agy").arbiter is None


def test_cascade_validation_and_spec_parsing():
    with pytest.raises(ValueError, match="two providers"):
        Cascade(2, (JudgeSpec("claude"), JudgeSpec("claude")))
    with pytest.raises(ValueError, match="needs an arbiter"):
        Cascade(3, (JudgeSpec("claude"), JudgeSpec("agy")))
    with pytest.raises(ValueError, match="takes 1"):
        Cascade(1, (JudgeSpec("claude"), JudgeSpec("agy")))
    assert JudgeSpec.parse("agy:gemini-3.1-pro:high") == JudgeSpec("agy", "gemini-3.1-pro", "high")
    assert JudgeSpec.parse("claude") == JudgeSpec("claude", None, "low")
    assert JudgeSpec.parse("codex:-:high") == JudgeSpec("codex", None, "high")
    with pytest.raises(ValueError, match="unknown judge provider"):
        JudgeSpec.parse("vertex")
    with pytest.raises(ValueError, match="judge <run-id>"):
        judge.parse_judges("rules,llm")


# ---------------------------------------------------------------------------
# One message through the cascade (judges faked, no CLI)
# ---------------------------------------------------------------------------


def _contact():
    conn = data_mod.connect()
    try:
        pick = picker.build_pick(conn, name="t")
        cid = next(int(i) for i, f in pick["contacts"].items() if f["tier"] == "linked")
        return data_mod.load_contact(conn, cid)
    finally:
        conn.close()


@needs_db
@pytest.mark.asyncio
async def test_level_3_calls_the_arbiter_with_both_verdicts(monkeypatch):
    contact = _contact()
    message = (
        f"{contact.name_vocative},\n\nmáme pro Vás nabídku."
        if contact.formal
        else f"{contact.name_vocative},\n\nmáme pro tebe nabídku."
    )
    seen: list[tuple[str, str | None, int]] = []

    async def fake(message, contact, spec, *, role="judge", prior=None, timeout=180):
        seen.append((role, spec.provider, len(prior or [])))
        ok = spec.provider != "agy"  # agy disagrees
        v = _verdict("FULL", ok, role=role, provider=spec.provider)
        return v

    monkeypatch.setattr(judge, "judge_with_model", fake)
    result = await judge_cascade(message, contact, default_cascade(3, "codex"))
    assert [s[0] for s in seen] == ["judge", "judge", "arbiter"]
    assert seen[2] == ("arbiter", "codex", 2)  # the arbiter saw both prior verdicts
    assert result.final == FINAL_VALID and result.reason == "arbiter_valid" and result.calls == 3

    seen.clear()
    result2 = await judge_cascade(message, contact, default_cascade(2, "codex"))
    assert [s[0] for s in seen] == ["judge", "judge"]
    assert (
        result2.final == FINAL_HUMAN
        and result2.reason == "judges_disagree"
        and result2.arbiter is None
    )


# ---------------------------------------------------------------------------
# The second pass over a run folder
# ---------------------------------------------------------------------------


def _pick():
    conn = data_mod.connect()
    try:
        return picker.build_pick(conn, name="test-pick")
    finally:
        conn.close()


@needs_db
def test_judge_run_writes_a_folder_beside_the_run(tmp_path):
    folder = runner.run(_pick(), levels_spec="1,2", provider="mock", runs_dir=tmp_path, run_id="r")
    out = judge_run.judge_run(
        "r", default_cascade(3, "mock"), runs_dir=tmp_path, judge_id="judge-t"
    )
    assert out == folder / "judge-t"
    assert {p.name for p in out.iterdir()} == {
        "config.json",
        "verdicts.jsonl",
        "summary.json",
        "human-review.md",
    }
    assert {p.name for p in folder.iterdir()} >= {"config.json", "messages.jsonl", "summary.json"}
    config = json.loads((out / "config.json").read_text(encoding="utf-8"))
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    n = sum(1 for _ in (folder / "messages.jsonl").open(encoding="utf-8"))
    # the mock judge is FULL and valid, so every message composes VALID with two calls
    assert config["messages"] == n and summary["total"][FINAL_VALID] == n
    assert summary["total"]["calls"] == 2 * n and summary["total"]["arbitrations"] == 0
    assert summary["total"]["judge_agreement"] == 1.0
    assert "To decide (HUMAN): 0" in (out / "human-review.md").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        judge_run.judge_run("r", default_cascade(3, "mock"), runs_dir=tmp_path, judge_id="judge-t")


@needs_db
def test_human_sheet_lists_the_rows_to_decide(tmp_path, monkeypatch):
    runner.run(_pick(), levels_spec="1", provider="mock", runs_dir=tmp_path, run_id="r2")

    async def disagreeing(message, contact, spec, *, role="judge", prior=None, timeout=180):
        return _verdict(
            "FULL",
            spec.provider != "agy" if role == "judge" else False,
            role=role,
            provider=spec.provider,
        )

    monkeypatch.setattr(judge, "judge_with_model", disagreeing)
    out = judge_run.judge_run(
        "r2", default_cascade(3, "codex"), runs_dir=tmp_path, judge_id="judge-d"
    )
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert (
        summary["total"][FINAL_HUMAN] == summary["total"]["n"]
        and summary["total"]["arbitrations"] == summary["total"]["n"]
    )
    sheet = (out / "human-review.md").read_text(encoding="utf-8")
    assert (
        "arbiter_invalid" in sheet
        and "**Human verdict:**" in sheet
        and "| arbiter | codex" in sheet
    )


@needs_db
def test_judge_run_subset_is_filtered_and_recorded(tmp_path):
    pick = _pick()
    runner.run(pick, levels_spec="1", provider="mock", runs_dir=tmp_path, run_id="r3")
    cid = pick["reading_set"][0]
    out = judge_run.judge_run(
        "r3",
        default_cascade(1, "mock"),
        runs_dir=tmp_path,
        judge_id="j",
        contacts=[cid],
        briefs=[pick["briefs"][0]],
    )
    config = json.loads((out / "config.json").read_text(encoding="utf-8"))
    assert config["messages"] == 1 and config["subset"] == {
        "contacts": [cid],
        "briefs": [pick["briefs"][0]],
    }
    with pytest.raises(ValueError, match="nothing to judge"):
        judge_run.judge_run(
            "r3", default_cascade(1, "mock"), runs_dir=tmp_path, judge_id="j2", contacts=[-1]
        )


def test_span_check_reads_quotes_fragments_and_explanations():
    """Live judges quote in three shapes (smoke 2026-09-05); all three are real quotes."""
    from ucs.uc01_personalization.judge import evidence_fragments

    msg = "Vážený pane Sedláčku, 🔥 výprodej startuje TEĎ!! Tají před očima rychleji, než čekáte. Tohle je Vaše šance konečně pořídit, co jste odkládal. Neotálejte — nakupujte dřív!"
    # a quote followed by an explanation after a dash (claude)
    assert (
        span_status(
            '"Vážený pane Sedláčku," — zpráva začíná přesně zadaným oslovením a neopakuje ho', msg
        )
        == "found"
    )
    # several fragments joined with ";" (agy, codex)
    assert span_status("než čekáte; Vaše šance; jste odkládal; Neotálejte", msg) == "found"
    # several quoted pieces, one of them not in the text -> missing
    assert span_status('"než čekáš", "co jsi odkládal"', msg) == "missing"
    assert span_status('"než čekáte", "co jste odkládal"', msg) == "found"
    # a paraphrase stays missing; an ellipsis inside a quote is tolerated
    assert span_status("co jste odkládala", msg) == "missing"
    assert (
        span_status("Tohle je Vaše šance … co jste odkládal", msg) == "missing"
    )  # two pieces? no: one span with a gap
    assert evidence_fragments('"Ahoj Lukáši," — zpráva začíná přesně') == ["Ahoj Lukáši,"]
    assert evidence_fragments("čekáš; tvoje šance; jsi odkládal") == [
        "čekáš",
        "tvoje šance",
        "jsi odkládal",
    ]


@needs_db
def test_na_on_an_assessable_criterion_is_a_dodge():
    """Live smoke 2026-09-05: a judge wrote "neposuzováno" for gender although gender was stored."""
    from ucs.uc01_personalization.judge import assessable_criteria

    v = evaluate_judge_json(
        _json(g="neposuzováno"),
        MSG,
        role="judge",
        provider="claude",
        model="m",
        tier="low",
        assessable={"vocative", "register", "gender"},
    )
    assert v.spans["gender"] == "missing" and v.status == "PARTIAL"
    v2 = evaluate_judge_json(
        _json(g="neposuzováno"),
        MSG,
        role="judge",
        provider="claude",
        model="m",
        tier="low",
        assessable={"vocative", "register"},
    )
    assert v2.spans["gender"] == "n/a" and v2.status == "FULL"
    contact = _contact()
    assert "vocative" in assessable_criteria(contact)
    # comma-joined fragments (the pre-1.2.0 agy style) are read as fragments too
    assert (
        span_status(
            "čekáte, Vaše šance, jste odkládala",
            "než čekáte. Tohle je Vaše šance, co jste odkládala.",
        )
        == "found"
    )
