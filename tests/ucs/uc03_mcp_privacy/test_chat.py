"""Provider continuation and final restoration without live model calls."""

import json

import pytest

from tests.ucs.uc03_mcp_privacy.conftest import stub_detector
from ucs.uc03_mcp_privacy import chat
from ucs.uc03_mcp_privacy.envelope import SessionEnvelope
from utils.generation import agy_mcp, codex_mcp


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider, host, model",
    [
        ("codex", codex_mcp, "gpt-5.6-luna"),
        ("agy", agy_mcp, "gemini-3.8-flash"),
    ],
)
async def test_session_resumes_and_invalid_answer_does_not_replay(
    tmp_path, monkeypatch, provider, host, model
):
    monkeypatch.setattr(chat.config, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(
        chat, "SessionEnvelope", lambda path: SessionEnvelope(path, detector=stub_detector)
    )
    calls = []

    async def fake_host(**kwargs):
        calls.append(kwargs)
        assert "Novák" not in kwargs["prompt"]
        if len(calls) == 1:
            text = kwargs["prompt"]
        else:
            text = "<PERSON_0>"
        return {"text": text, "session_id": "native-id", "tool_calls": []}

    monkeypatch.setattr(host, "generate_with_mcp", fake_host)
    common = dict(session="probe", profile="strict", model=model, provider=provider, tier="low")
    first = await chat.run_turn("Najdi Jan Novák", **common)
    assert first["answer"] == "Najdi Jan Novák" and first["restoration"]["ok"]
    second = await chat.run_turn("Shrň nákup", resume=True, **common)
    assert calls[0]["resume"] is False
    assert calls[1]["resume"] is True and calls[1]["session_id"] == "native-id"
    assert len(calls) == 2
    assert second["restoration"]["error"] == "unknown_token"
    assert "<PERSON_0>" not in second["answer"]
    state = json.loads((tmp_path / "sessions" / "probe" / "provider-session.json").read_text())
    assert state["provider"] == provider


@pytest.mark.asyncio
async def test_agy_inventory_reads_the_real_pinned_stdio_server(scratch_db, tmp_path):
    import sys
    from utils.paths import THESIS_ROOT
    from ucs.uc03_mcp_privacy.tools import TOOL_NAMES

    names = await agy_mcp._tool_names(
        {
            "command": sys.executable,
            "args": ["-m", "ucs.uc03_mcp_privacy.server"],
            "cwd": str(THESIS_ROOT),
            "env": {
                "PYTHONPATH": str(THESIS_ROOT),
                "UC03_DB_PATH": str(scratch_db),
                "UC03_SECURITY": "strict",
                "UC03_SESSION_MAP": str(tmp_path / "map.json"),
                "UC03_AUDIT_PATH": str(tmp_path / "audit.jsonl"),
            },
        }
    )
    assert names == set(TOOL_NAMES)
