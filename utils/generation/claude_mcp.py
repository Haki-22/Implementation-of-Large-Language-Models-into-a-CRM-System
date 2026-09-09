"""Claude CLI wrapper for MCP-enabled prompts.

Built atop ``claude.py``: same Linux argv ceiling handling, same subprocess
retries, same typed errors. Adds ``--mcp-config`` and ``--allowedTools``
flag pass-through so the chat LLM can call tools exposed by a registered
MCP server.

Use this for any caller that needs the LLM to *act* on data (CRM tool
calls, file lookups, etc.) rather than just generate text. For pure text
generation in the chapter pipeline, keep using ``claude.generate_text``.

Example (FastAPI demo backend)
------------------------------
.. code-block:: python

    from utils.generation.claude_mcp import generate_with_mcp

    result = await generate_with_mcp(
        prompt="Najdi mi kontakt s příjmením Novák.",
        mcp_config_path="/abs/path/to/mcp-config.json",
        allowed_tools=["mcp__uc03__search_contacts"],
        model="sonnet",
    )
    print(result["text"])          # final assistant message
    for call in result["tool_calls"]:
        print(call.tool_name, call.input, call.output)

Latency note
------------
Roughly 30-90 s per call: claude CLI startup + MCP server spawn +
handshake + LLM thinking + each tool round-trip. For interactive UIs
surface a "Přemýšlí…" indicator while awaiting.
"""

from __future__ import annotations

from typing import Any

from utils.generation.claude import (
    DEFAULT_TIMEOUT_SECONDS,
    _build_args,
    _build_prompt,
    _run_claude,
)
from utils.generation.mcp_types import McpCall

# Claude Code's built-in tools. The MCP demo exposes a *closed* CRM tool
# surface (the ``mcp__<server>__*`` whitelist); the model must never reach
# for the local filesystem, shell, or network. Denying these by default
# means a prompt injection arriving through tool data (a CRM note, a voice
# transcript, a product title) cannot escalate into file exfiltration or
# command execution — it can only ever call the whitelisted MCP tools.
# This is the same threat the project studies, so the demo itself must not
# be the weak link. Callers can override via ``disallowed_tools=[]`` but
# should not for the published build.
_DENY_BUILTIN_TOOLS: tuple[str, ...] = (
    "Bash",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
    "LS",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
    "KillShell",
    "BashOutput",
)


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
    """Run ``claude -p`` with MCP servers attached so the LLM can call tools.

    Parameters
    ----------
    prompt
        User content (Czech OK).
    mcp_config_path
        Absolute path to a JSON file with the ``mcpServers`` mapping —
        same shape as Claude Desktop's ``claude_desktop_config.json``.
    allowed_tools
        Optional whitelist of tool names. Format: ``mcp__<server>__<tool>``.
        When ``None`` all configured MCP tools plus Claude's built-ins are
        allowed; pass an explicit list to constrain the surface.
    disallowed_tools
        Tool names the model may never call. Defaults to
        ``_DENY_BUILTIN_TOOLS`` — every Claude Code built-in (shell, file
        I/O, web) — so the demo's tool surface is closed to the MCP
        whitelist alone and injected tool data cannot escalate. Pass an
        explicit list to override, or ``[]`` to disable the deny-list
        (not recommended for a shared / published build).
    system_prompt
        Optional system-level guidance, passed through ``--system-prompt``
        separately from the masked user request.
    model
        ``"haiku"`` / ``"sonnet"`` / ``"opus"`` or a full model ID. ``None``
        falls back to ``claude.DEFAULT_MODEL``.
    timeout
        Seconds. ``None`` uses ``claude.DEFAULT_TIMEOUT_SECONDS`` (90 s).
    session_id
        A UUID that names the CLI conversation. The first turn of a chat passes
        it with ``resume=False`` (``--session-id``); every later turn passes the
        same id with ``resume=True`` (``--resume``), and the model then sees the
        earlier turns and tool results of that conversation. ``None`` keeps the
        one-shot behaviour: a fresh conversation per call.
    resume
        Continue the conversation ``session_id`` names instead of starting it.

    Returns
    -------
    dict
        Four keys:

        - ``"text"`` (str): the assistant's final text response.
        - ``"tool_calls"`` (list[McpCall]): MCP tool invocations parsed
          from the transcript, paired with their results.
        - ``"session_id"`` (str | None): the conversation id the CLI reports.
        - ``"raw"`` (dict): the full claude JSON envelope, for callers
          that need cost, usage, or transcript inspection.
    """
    effective_prompt, native_sp = _build_prompt(prompt, system_prompt, mode="native")

    extra: list[str] = ["--mcp-config", mcp_config_path]
    if allowed_tools:
        extra += ["--allowedTools", ",".join(allowed_tools)]
    if session_id:
        extra += ["--resume", session_id] if resume else ["--session-id", session_id]

    # Closed tool surface: deny every built-in unless the caller opts out.
    # ``None`` -> default deny-list; ``[]`` -> explicit opt-out (no flag).
    effective_deny = list(_DENY_BUILTIN_TOOLS) if disallowed_tools is None else disallowed_tools
    if effective_deny:
        extra += ["--disallowedTools", ",".join(effective_deny)]

    args, stdin_input = _build_args(
        effective_prompt,
        model=model,
        tier=tier,
        system_prompt_native=native_sp,
        extra_args=extra,
    )

    envelope = await _run_claude(
        args,
        timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
        stdin_input=stdin_input,
    )

    return {
        "text": envelope.get("result", ""),
        "tool_calls": _extract_tool_calls(envelope),
        "session_id": envelope.get("session_id"),
        "raw": envelope,
    }


def _extract_tool_calls(envelope: dict[str, Any]) -> list[McpCall]:
    """Walk the ``claude -p`` JSON envelope and collect MCP tool invocations.

    The envelope's transcript-like field contains a sequence of message
    events. ``tool_use`` blocks carry the tool name + input arguments;
    paired ``tool_result`` blocks (matched by ``tool_use_id``) carry the
    output. Tool calls that are not MCP (e.g. claude's built-in ``Read``
    or ``Bash``) are skipped.

    The shape of ``claude -p --output-format json`` has varied across
    CLI versions, so this routine defensively probes several common paths
    and tolerates missing fields.
    """
    calls: list[McpCall] = []
    pending: dict[str, McpCall] = {}

    transcript = (
        envelope.get("transcript") or envelope.get("messages") or envelope.get("events") or []
    )

    for event in transcript:
        if not isinstance(event, dict):
            continue
        message = event.get("message") if isinstance(event.get("message"), dict) else event
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                name = block.get("name") or ""
                if not name.startswith("mcp__"):
                    continue
                call = McpCall(
                    tool_name=name,
                    input=block.get("input") if isinstance(block.get("input"), dict) else {},
                )
                pending[block.get("id") or ""] = call
                calls.append(call)
            elif btype == "tool_result":
                tool_use_id = block.get("tool_use_id") or ""
                call = pending.get(tool_use_id)
                if call is None:
                    continue
                result_content = block.get("content")
                if isinstance(result_content, str):
                    call.output = result_content
                elif isinstance(result_content, list):
                    texts = [
                        b.get("text", "")
                        for b in result_content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    call.output = "\n".join(t for t in texts if t) or None

    return calls
