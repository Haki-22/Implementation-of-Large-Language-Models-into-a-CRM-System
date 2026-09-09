"""MCP adapter contract: isolated configuration, tool events and continuation."""

import json

import pytest

from utils.generation import codex_mcp


@pytest.mark.asyncio
async def test_codex_mcp_isolated_arguments_and_continuation(tmp_path, monkeypatch):
    config = tmp_path / "mcp-config.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "uc03": {
                        "command": "python",
                        "args": ["-m", "server"],
                        "env": {"UC03_SECURITY": "strict"},
                    }
                }
            }
        )
    )
    invocations = []

    async def fake_run(args, output_file, timeout, stdin_text, *, events):
        invocations.append(args)
        events.extend(
            [
                {"type": "thread.started", "thread_id": "native-codex-id"},
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "uc03",
                        "tool": "search_contacts",
                        "arguments": {"query": "<PERSON_42>"},
                        "result": {"ok": True},
                        "status": "completed",
                    },
                },
            ]
        )
        return "answer"

    monkeypatch.setattr(codex_mcp, "_run_codex", fake_run)
    options = dict(
        mcp_config_path=str(config),
        allowed_tools=["mcp__uc03__search_contacts"],
        system_prompt="CRM instructions",
        model="gpt-5.6-luna",
        tier="low",
    )
    first = await codex_mcp.generate_with_mcp("first turn", **options)
    assert first["session_id"] == "native-codex-id"
    assert first["tool_calls"][0].input == {"query": "<PERSON_42>"}
    await codex_mcp.generate_with_mcp(
        "next turn", session_id=first["session_id"], resume=True, **options
    )
    for args in invocations:
        assert "--ignore-user-config" in args
        assert "--dangerously-bypass-approvals-and-sandbox" not in args
        assert 'sandbox_mode="read-only"' in args
        assert 'developer_instructions="CRM instructions"' in args
        assert any("enabled_tools" in item and "search_contacts" in item for item in args)
        assert args[args.index("--model") + 1] == "gpt-5.6-luna"
    assert invocations[1][:3] == ["codex", "exec", "resume"]
    assert invocations[1][-2:] == ["native-codex-id", "next turn"]
