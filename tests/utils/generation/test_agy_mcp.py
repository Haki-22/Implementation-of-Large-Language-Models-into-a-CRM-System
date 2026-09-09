"""Antigravity MCP host contract, without any external model calls."""

import inspect
import json
from pathlib import Path

import pytest

from utils.generation import agy_mcp, claude_mcp, codex_mcp
from utils.generation.errors import ProviderAuthError, ProviderOutputError


@pytest.fixture
def config(tmp_path):
    """A minimal ``mcp-config.json`` under ``tmp_path`` with one ``uc03`` server entry."""
    path = tmp_path / "mcp-config.json"
    path.write_text(
        json.dumps({"mcpServers": {"uc03": {"command": "python", "args": ["server.py"]}}})
    )
    return path


def test_all_mcp_hosts_share_the_claude_call_signature():
    expected = inspect.signature(claude_mcp.generate_with_mcp)
    assert inspect.signature(codex_mcp.generate_with_mcp) == expected
    assert inspect.signature(agy_mcp.generate_with_mcp) == expected


@pytest.mark.asyncio
async def test_agy_uses_mcp_only_agent_and_native_continuation(config, monkeypatch):
    calls = []

    async def inventory(server):
        return {"search_contacts", "get_contact", "create_note"}

    async def runner(args, timeout, *, cwd):
        calls.append((args, cwd))
        assert timeout == 60
        workspace = Path(cwd)
        doc = json.loads((workspace / ".agents" / "mcp_config.json").read_text())
        assert doc["mcpServers"]["foreign"] == {"disabled": True}
        assert doc["mcpServers"]["uc03"]["disabledTools"] == ["create_note", "get_contact"]
        agent = (workspace / ".agents" / "agents" / "uc03-crm.md").read_text()
        assert "tools: []" in agent and "inheritMcp: true" in agent
        assert "commandExecutionPolicy: off" in agent and "subagent: false" in agent
        assert "CRM system instructions" in agent
        return json.dumps(
            {"status": "SUCCESS", "response": "Answer", "conversation_id": "native-agy-id"}
        )

    monkeypatch.setattr(agy_mcp, "_tool_names", inventory)
    monkeypatch.setattr(agy_mcp, "_global_servers", lambda: {"foreign": {"command": "unused"}})
    monkeypatch.setattr(agy_mcp, "_run_agy", runner)
    options = dict(
        mcp_config_path=str(config),
        allowed_tools=["mcp__uc03__search_contacts", "mcp__uc03__get_contact"],
        disallowed_tools=["mcp__uc03__get_contact"],
        system_prompt="CRM system instructions",
        model="gemini-3.8-flash",
        tier="low",
        timeout=60,
    )
    first = await agy_mcp.generate_with_mcp("<PERSON_42>", **options)
    second = await agy_mcp.generate_with_mcp(
        "Next turn", session_id=first["session_id"], resume=True, **options
    )
    assert first["text"] == "Answer" and second["tool_calls"] == []
    assert {"text", "tool_calls", "session_id", "raw"} <= first.keys()
    assert "--new-project" in calls[0][0] and "--new-project" not in calls[1][0]
    assert calls[1][0][-2:] == ["--conversation", "native-agy-id"]
    for args, cwd in calls:
        assert args[args.index("--model") + 1] == "gemini-3.8-flash-low"
        assert "--dangerously-skip-permissions" not in args
        assert "--sandbox" in args and "--disable-slash-commands" in args
        assert Path(cwd) == config.parent / "agy-workspace"
        assert "CRM system instructions" not in args


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response, error",
    [
        (
            {"response": "", "denied_actions": [{"action": "mcp", "display_name": "CallMcpTool"}]},
            ProviderAuthError,
        ),
        ({"response": ""}, ProviderOutputError),
        ({}, ProviderOutputError),
        ({"response": "Answer", "conversation_id": None}, ProviderOutputError),
    ],
)
async def test_agy_refuses_denied_or_incomplete_envelopes(config, monkeypatch, response, error):
    count = 0

    async def inventory(server):
        return {"search_contacts"}

    async def runner(*args, **kwargs):
        nonlocal count
        count += 1
        return json.dumps({"status": "SUCCESS", "conversation_id": "native", **response})

    monkeypatch.setattr(agy_mcp, "_tool_names", inventory)
    monkeypatch.setattr(agy_mcp, "_global_servers", lambda: {})
    monkeypatch.setattr(agy_mcp, "_run_agy", runner)
    with pytest.raises(error):
        await agy_mcp.generate_with_mcp("Request", mcp_config_path=str(config))
    assert count == 1


@pytest.mark.asyncio
async def test_agy_refuses_unknown_allowlist_before_model(config, monkeypatch):
    async def inventory(server):
        return {"search_contacts"}

    async def runner(*args, **kwargs):
        pytest.fail("Model must not be called for an unknown tool")

    monkeypatch.setattr(agy_mcp, "_tool_names", inventory)
    monkeypatch.setattr(agy_mcp, "_global_servers", lambda: {})
    monkeypatch.setattr(agy_mcp, "_run_agy", runner)
    with pytest.raises(ValueError, match="unknown MCP tool"):
        await agy_mcp.generate_with_mcp(
            "Request", mcp_config_path=str(config), allowed_tools=["mcp__uc03__missing"]
        )
    with pytest.raises(ValueError, match="conversation id"):
        await agy_mcp.generate_with_mcp("Request", mcp_config_path=str(config), resume=True)
