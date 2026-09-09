"""CRM instructions and selected effort reach the native Claude host separately."""

import pytest

from utils.generation import claude_mcp
from utils.generation.claude import normalize_model


@pytest.mark.asyncio
async def test_native_system_prompt_and_selected_effort(monkeypatch):
    invocations = []

    async def fake_run(args, **kwargs):
        invocations.append(args)
        return {"result": "answer", "session_id": "native-id"}

    monkeypatch.setattr(claude_mcp, "_run_claude", fake_run)
    result = await claude_mcp.generate_with_mcp(
        "<PERSON_42>",
        mcp_config_path="config.json",
        allowed_tools=["mcp__uc03__search_contacts"],
        system_prompt="CRM instructions",
        model="sonnet",
        tier="low",
    )
    args = invocations[0]
    assert args[args.index("--system-prompt") + 1] == "CRM instructions"
    assert args[args.index("--effort") + 1] == "low"
    assert args[args.index("--model") + 1] == normalize_model("sonnet")
    assert "<PERSON_42>" in args
    assert result["text"] == "answer"
