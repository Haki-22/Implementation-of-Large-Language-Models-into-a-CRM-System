"""Codex as a persistent MCP host with a per-conversation tool allow-list.

Uses the existing CLI dispatcher and login. User configuration, plugins, shell
and browser tools are disabled for this CRM conversation; only the configured
MCP server is connected. No global Codex configuration is changed.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from utils.generation.codex import _run_codex, normalize_model, normalize_tier, prompt_transport
from utils.generation.errors import ProviderOutputError
from utils.generation.mcp_types import McpCall


def _toml(value: Any) -> str:
    """Encode the strings, lists and tables used by per-invocation -c options."""
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(json.dumps(key) + "=" + _toml(item) for key, item in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


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
    """Run or resume one CRM turn; return text, observed calls and native session id."""
    config_path = Path(mcp_config_path).resolve()
    timeout = timeout or 300
    folder = config_path.parent
    model = normalize_model(model)
    tier = normalize_tier(tier, model)
    servers = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]
    options: dict[str, Any] = {
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        "sandbox_mode": "read-only",
    }
    if system_prompt is not None:
        options["developer_instructions"] = system_prompt
    if tier is not None:
        options["model_reasoning_effort"] = tier
    for name, server in servers.items():
        prefix = f"mcp__{name}__"
        names = (
            [tool.removeprefix(prefix) for tool in allowed_tools if tool.startswith(prefix)]
            if allowed_tools is not None
            else None
        )
        if names == []:
            raise ValueError(f"No tools allowed for MCP server {name}")
        options[f"mcp_servers.{name}"] = {
            **server,
            **({"enabled_tools": names} if names is not None else {}),
            "disabled_tools": sorted(
                set(server.get("disabled_tools", []))
                | {
                    tool.removeprefix(prefix)
                    for tool in (disallowed_tools or [])
                    if tool.startswith(prefix)
                }
            ),
            "required": True,
            "default_tools_approval_mode": "approve",
            "startup_timeout_sec": 30,
            "tool_timeout_sec": timeout,
        }
    args = ["codex", "exec"]
    if resume:
        if not session_id:
            raise ValueError("Cannot resume without the Codex conversation id")
        args.append("resume")
    else:
        args += ["--cd", str(folder)]
    output_file = str(folder / f"codex-answer-{uuid.uuid4().hex}.txt")
    args += [
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--json",
        "--model",
        model,
        "--output-last-message",
        output_file,
    ]
    for feature in (
        "shell_tool",
        "multi_agent",
        "apps",
        "plugins",
        "memories",
        "hooks",
        "browser_use",
        "computer_use",
        "image_generation",
        "view_image",
    ):
        args += ["--disable", feature]
    for key, value in options.items():
        args += ["-c", key + "=" + _toml(value)]
    if resume:
        args.append(session_id)
    prompt_arg, stdin_text = prompt_transport(prompt)
    args.append(prompt_arg)
    events: list[dict] = []
    text = await _run_codex(args, output_file, timeout, stdin_text, events=events)
    calls = []
    native_session = session_id
    for event in events:
        if event.get("type") == "thread.started":
            native_session = event["thread_id"]
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
            calls.append(
                McpCall(
                    tool_name=f"mcp__{item['server']}__{item['tool']}",
                    input=item.get("arguments", {}),
                    output=json.dumps(item.get("result") or item.get("error"), ensure_ascii=False),
                )
            )
    if not native_session:
        raise ProviderOutputError("codex", "MCP host did not return a conversation id")
    return {
        "text": text,
        "tool_calls": calls,
        "session_id": native_session,
        "raw": {"events": events},
        "model": model,
        "tier": tier,
    }
