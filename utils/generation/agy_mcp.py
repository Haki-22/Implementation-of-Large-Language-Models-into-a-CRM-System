"""Antigravity CLI MCP host, using the same call contract as claude_mcp/codex_mcp.

Uses agy's existing dispatcher and login. A dedicated primary agent has no
built-in tools and inherits the workspace's MCP definitions. The private host
workspace is a child of the session directory, outside the token map/database.
Tool permissions must be granted by the operator; this adapter never edits
global permissions or bypasses approval. agy's JSON has no tool transcript,
so UC-03 obtains observed calls from its server audit, as it does for Claude.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from utils.generation.agy import (
    _build_args,
    _run_agy,
    _text_from_envelope,
    normalize_tier,
    split_model,
)
from utils.generation.errors import ProviderAuthError, ProviderOutputError


async def _tool_names(server: dict[str, Any]) -> set[str]:
    """Discover the stdio inventory so agy's deny-list implements our allow-list."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        cwd=server.get("cwd"),
        env={**os.environ, **server.get("env", {})},
    )
    names: set[str] = set()
    async with asyncio.timeout(30):
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                cursor = None
                while True:
                    result = await session.list_tools(cursor=cursor)
                    names.update(tool.name for tool in result.tools)
                    cursor = result.nextCursor
                    if not cursor:
                        return names


def _global_servers() -> dict[str, Any]:
    """Read names only; workspace disables unrelated global servers without editing them."""
    path = Path.home() / ".gemini" / "config" / "mcp_config.json"
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    return json.loads(text).get("mcpServers", {}) if text else {}


async def generate_with_mcp(
    prompt: str,
    *,
    mcp_config_path: str,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    tier: str | None = None,
    timeout: int | None = None,
    session_id: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run or resume one turn; return text, tool_calls, native session_id and raw envelope.

    MCP names use ``mcp__server__tool`` in both allow/deny lists. Built-ins are
    always excluded, even with an empty explicit deny-list. No automatic retry:
    a failed response may follow a successful CRM mutation.
    """
    if resume and not session_id:
        raise ValueError("Cannot resume without the agy conversation id")
    timeout = timeout or 300
    model, suffix = split_model(model)
    tier = normalize_tier(suffix if suffix is not None else tier, model)
    config_path = Path(mcp_config_path).resolve()
    servers = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]
    workspace = config_path.parent / "agy-workspace"
    agent_dir = workspace / ".agents" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    configured = {name: {"disabled": True} for name in _global_servers() if name not in servers}
    for name, server in servers.items():
        prefix = f"mcp__{name}__"
        inventory = await _tool_names(server)
        allowed = (
            {tool.removeprefix(prefix) for tool in allowed_tools if tool.startswith(prefix)}
            if allowed_tools is not None
            else inventory
        )
        if not allowed or allowed - inventory:
            raise ValueError(f"Empty or unknown MCP tool allow-list for {name}")
        denied = {
            tool.removeprefix(prefix)
            for tool in (disallowed_tools or [])
            if tool.startswith(prefix)
        }
        configured[name] = {
            **server,
            "disabledTools": sorted(
                (inventory - allowed) | denied | set(server.get("disabledTools", []))
            ),
        }
    (workspace / ".agents" / "mcp_config.json").write_text(
        json.dumps({"mcpServers": configured}, indent=2), encoding="utf-8"
    )
    (agent_dir / "uc03-crm.md").write_text(
        "---\nname: uc03-crm\ndescription: CRM assistant using only configured MCP tools\n"
        "mainAgent: true\nsubagent: false\ntools: []\ninheritMcp: true\n"
        "commandExecutionPolicy: off\n---\n"
        + (system_prompt or "Use the configured MCP tools.")
        + "\n",
        encoding="utf-8",
    )
    args = _build_args(prompt, model=model, tier=tier, timeout=timeout)
    args += ["--disable-slash-commands", "--sandbox", "--agent", "uc03-crm"]
    args += ["--conversation", session_id] if resume else ["--new-project"]
    raw = await _run_agy(args, timeout, cwd=str(workspace))
    text, envelope = _text_from_envelope(raw)
    if envelope and envelope.get("denied_actions"):
        raise ProviderAuthError(
            "agy",
            "MCP host denied a tool action; no automatic retry was made.",
            hint="Grant the specific uc03 MCP tool in agy permissions, then inspect the audit before retrying.",
            details=json.dumps(envelope["denied_actions"], ensure_ascii=False),
        )
    if (
        not text
        or not envelope
        or not isinstance(envelope.get("response"), str)
        or not envelope.get("conversation_id")
    ):
        raise ProviderOutputError("agy", "MCP host returned no answer or conversation id")
    return {
        "text": text,
        "tool_calls": [],
        "session_id": envelope["conversation_id"],
        "raw": envelope,
        "model": model,
        "tier": tier,
    }
