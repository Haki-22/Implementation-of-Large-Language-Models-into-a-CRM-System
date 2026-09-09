"""
Claude Code CLI provider for `utils.generation`.

This module calls Claude in non-interactive mode:

    claude -p <prompt> --model <model> --effort <tier> --output-format json

Model options:
    Aliases (`sonnet`, `opus`, `haiku`, `fable`, `best`, `default`) or full ids
    (`claude-sonnet-5`, `claude-opus-5[1m]`) from the generated
    `utils/generation/models.py` (`CLAUDE_ALIASES`, `CLAUDE_MODELS`), which
    mirrors the alias map compiled into the installed Claude Code binary at
    catalog time. Aliases resolve to the concrete id before the call, so run
    folders record `claude-sonnet-5`, never `sonnet`. Anything outside the menu
    is refused with a hint to run `python -m utils.generation.catalog update`.
    The thesis default is DEFAULT_MODEL below; the vendor's own menu default is
    `CLAUDE_VENDOR_DEFAULT`.

Tier options:
    low, medium, high, xhigh, max

System prompts:
    `native` uses Claude's --system-prompt flag.
    `concat` prepends the system prompt to the user prompt.

Structured output:
    `generate_json()` passes an inline JSON Schema to --json-schema and reads
    Claude's schema-validated `structured_output` field from the CLI JSON
    envelope.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

from utils import llm_switch
from utils.generation.catalog import UPDATE_COMMAND
from utils.generation.errors import (
    GenerationError,
    ProviderJsonError,
    ProviderTimeoutError,
    classify_cli_failure,
    cli_missing,
)
from utils.generation.models import CLAUDE_ALIASES, CLAUDE_MODELS, CLAUDE_TIER_OPTIONS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER_OPTIONS: tuple[str, ...] = CLAUDE_TIER_OPTIONS
# Thesis default (the vendor's menu default is CLAUDE_VENDOR_DEFAULT in models.py).
# Must resolve into CLAUDE_MODELS; tests/utils/generation/test_models_generated.py checks.
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SECONDS = 90

# Resolve absolute path to `claude` once at import time so concurrent subprocess
# spawns can't lose it under PATH races. Then realpath() through any symlinks
# (nvm installs `claude` as a symlink to a real binary `claude.exe` — under
# heavy parallel asyncio subprocess load the symlink resolution occasionally
# failed inside the kernel exec path, producing spurious FileNotFoundError.
# Targeting the real path avoids that race entirely).
_resolved = shutil.which("claude") or "claude"
try:
    _CLI_BIN = os.path.realpath(_resolved)
except OSError:
    _CLI_BIN = _resolved

# Number of automatic retries on subprocess-level FileNotFoundError (only).
# Transient errno=2 has been observed under high concurrency on nvm-managed
# Node binaries; a few-ms sleep clears it.
_CLI_EXEC_RETRIES = 3
_CLI_EXEC_RETRY_BACKOFF_S = 0.25

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_prompt(prompt: str, system_prompt: str | None, mode: str) -> tuple[str, str | None]:
    """
    Return (effective_prompt, native_system_prompt) based on mode.

    "concat" -- prepend system text to the prompt; native_system_prompt=None.
    "native" -- pass system text as a separate native arg; prompt unchanged.
    """
    if system_prompt is None:
        return prompt, None
    if mode == "concat":
        return f"{system_prompt}\n\n{prompt}", None
    if mode == "native":
        return prompt, system_prompt
    raise ValueError(
        f"Unknown system_prompt_mode {mode!r}. Valid values: 'concat' (default) | 'native'."
    )


def resolve_alias(model: str) -> str:
    """Follow the alias chain from the generated menu (`best` -> `fable` -> id)."""
    cur = model
    seen: set[str] = set()
    while cur in CLAUDE_ALIASES and cur not in seen:
        seen.add(cur)
        cur = CLAUDE_ALIASES[cur]
    return cur


def normalize_model(model: str | None) -> str:
    """
    Return the concrete model id that is sent to --model.

    Args:
        model: `None` (thesis default), an alias from `CLAUDE_ALIASES`, or an
            id from `CLAUDE_MODELS`.

    Returns:
        Concrete model id accepted by Claude Code (aliases resolved).

    Raises:
        ValueError: If the value does not resolve into `CLAUDE_MODELS`.
    """
    key = DEFAULT_MODEL if model is None else str(model).strip()
    resolved = resolve_alias(key)
    if resolved in CLAUDE_MODELS:
        return resolved

    valid = ", ".join(CLAUDE_MODELS)
    aliases = ", ".join(CLAUDE_ALIASES)
    raise ValueError(
        f"Unsupported Claude model {model!r}. Models in the generated catalog: {valid}; "
        f"aliases: {aliases}. If Claude Code serves it, run `{UPDATE_COMMAND}` and commit."
    )


def normalize_tier(tier: str | None, model: str | None = None) -> str | None:
    """
    Validate a Claude reasoning-effort tier.

    Args:
        tier: `None`, `"low"`, `"medium"`, `"high"`, `"xhigh"`, or `"max"`.
        model: Accepted for a uniform adapter signature; every Claude model
            takes the same effort ladder, so it is not consulted.

    Returns:
        Normalized tier string, or `None` to omit the flag.

    Raises:
        ValueError: If the tier is not supported by Claude Code.
    """
    if tier is None:
        return None

    resolved = str(tier).strip().lower()
    if resolved not in TIER_OPTIONS:
        valid = ", ".join(TIER_OPTIONS)
        raise ValueError(f"Unsupported Claude tier {tier!r}. Valid tiers: {valid}.")
    return resolved


# Linux MAX_ARG_STRLEN is 128 KiB per single argv. Use stdin once a single
# arg approaches that limit; leave a 10 KiB safety margin.
_ARGV_SINGLE_LIMIT = 100 * 1024


def _build_args(
    prompt: str,
    *,
    model: str | None,
    tier: str | None,
    system_prompt_native: str | None,
    extra_args: list[str] | None = None,
) -> tuple[list[str], str | None]:
    """Build the argument list for a `claude -p` call.

    Returns ``(args, stdin_input)`` — when ``stdin_input`` is not ``None``,
    the caller must pipe it to claude's stdin and OMIT the prompt from argv.
    This avoids the Linux ``MAX_ARG_STRLEN`` (128 KiB) ceiling on any single
    argv entry, which would otherwise raise ``OSError [Errno 7] Argument
    list too long`` when the prompt or system prompt is chapter-length.
    """
    resolved_model = normalize_model(model)
    resolved_tier = normalize_tier(tier)
    use_stdin_for_prompt = len(prompt) > _ARGV_SINGLE_LIMIT
    args: list[str] = [_CLI_BIN, "-p"]
    if not use_stdin_for_prompt:
        args.append(prompt)
    args += ["--model", resolved_model, "--dangerously-skip-permissions", "--output-format", "json"]
    if system_prompt_native is not None:
        # System prompt also subject to MAX_ARG_STRLEN — fall back to file flag
        # via --system-prompt; if it's too large the CLI itself accepts a
        # file-based variant. For now, accept the same ceiling and fail loudly.
        if len(system_prompt_native) > _ARGV_SINGLE_LIMIT:
            raise GenerationError(
                "claude",
                f"system_prompt is {len(system_prompt_native)} chars, "
                f"exceeds Linux argv single-arg limit of {_ARGV_SINGLE_LIMIT}. "
                "Inline the system prompt into the user prompt instead "
                "(system_prompt_mode='concat').",
            )
        args += ["--system-prompt", system_prompt_native]
    if resolved_tier is not None:
        args += ["--effort", resolved_tier]
    if extra_args:
        args += extra_args
    return args, (prompt if use_stdin_for_prompt else None)


async def _run_claude(
    args: list[str],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    stdin_input: str | None = None,
) -> dict[str, Any]:
    """
    Run the claude CLI and return the parsed JSON envelope.

    When ``stdin_input`` is provided, the prompt is piped to claude's stdin
    instead of argv — required for prompts exceeding Linux MAX_ARG_STRLEN
    (128 KiB), which otherwise raises OSError [Errno 7] Argument list too long.

    Raises a typed `GenerationError` on process error, timeout, or malformed output.
    """
    # NOTE: runtime `shutil.which()` check was removed — under heavy concurrent
    # subprocess load (many parallel asyncio.create_subprocess_exec calls) the
    # access(F_OK | X_OK) probe inside `which` failed spuriously on a valid
    # nvm-managed symlink, producing false ProviderCliNotFoundError on most
    # rows of a 300-call batch. If the binary is truly missing, subprocess
    # itself will raise FileNotFoundError below — we catch & re-classify.
    llm_switch.require_llm_calls("claude")
    stdin_kw = asyncio.subprocess.PIPE if stdin_input is not None else asyncio.subprocess.DEVNULL
    input_bytes = stdin_input.encode("utf-8") if stdin_input is not None else None
    proc = None
    last_exc: OSError | None = None
    # Retry on transient subprocess-spawn failures. Catch broader than just
    # FileNotFoundError: PermissionError (errno=13) was observed when the
    # claude-code self-updater atomically replaced the 240MB binary in the
    # middle of a long batch — the new file was briefly without +x.
    for attempt in range(_CLI_EXEC_RETRIES):
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=stdin_kw,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            break
        except (FileNotFoundError, PermissionError) as exc:
            last_exc = exc
            if attempt + 1 < _CLI_EXEC_RETRIES:
                await asyncio.sleep(_CLI_EXEC_RETRY_BACKOFF_S * (attempt + 1))
                continue
    if proc is None:
        raise cli_missing("claude", _CLI_BIN) from last_exc
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=input_bytes), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except Exception:
            pass
        raise ProviderTimeoutError(
            "claude",
            f"CLI timed out after {timeout}s.",
            hint="Try a simpler prompt, lower effort tier, or longer timeout.",
        ) from exc

    raw = (stdout_b or b"").decode(errors="replace").strip()
    stderr_text = (stderr_b or b"").decode(errors="replace").strip()

    if not raw:
        detail = stderr_text or f"exit code {proc.returncode}"
        raise classify_cli_failure("claude", detail, exit_code=proc.returncode)

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderJsonError(
            "claude",
            "CLI stdout was not valid JSON.",
            details=raw[:1000],
        ) from exc

    if envelope.get("is_error") or envelope.get("subtype") not in ("success", ""):
        err_detail = envelope.get("result") or stderr_text or envelope.get("subtype")
        raise classify_cli_failure("claude", str(err_detail), exit_code=proc.returncode)

    return envelope


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


async def generate_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | None = None,
    tier: str | None = None,
    timeout: int | None = None,
) -> str:
    """
    Generate a text response via `claude -p ... --output-format json`.

    Parameters
    ----------
    prompt : str
        User-content text sent to the model.
    system_prompt : str | None
        Optional system-level instruction.
    system_prompt_mode : str
        "concat" (default) -- prepend system text to prompt.
        "native" -- use --system-prompt flag.
    model : str | None
        Alias or id from the generated menu.  Examples: "sonnet", "haiku",
        "claude-opus-5[1m]".  None uses DEFAULT_MODEL.
    tier : str | None
        Effort level: "low" | "medium" | "high" | "xhigh" | "max".

    Returns
    -------
    str
        The model's text response from the "result" field of the JSON envelope.

    Raises
    ------
    RuntimeError
        On CLI error, timeout, or logical failure.
    """
    effective_prompt, native_sp = _build_prompt(prompt, system_prompt, system_prompt_mode)
    args, stdin_input = _build_args(
        effective_prompt, model=model, tier=tier, system_prompt_native=native_sp
    )
    envelope = await _run_claude(
        args,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS,
        stdin_input=stdin_input,
    )
    return str(envelope.get("result", ""))


async def generate_json(
    prompt: str,
    schema: dict,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | None = None,
    tier: str | None = None,
    timeout: int | None = None,
) -> dict:
    """
    Generate a structured JSON response via `claude -p ... --json-schema ...`.

    Parameters
    ----------
    prompt : str
        User-content text / instruction.
    schema : dict
        JSON Schema describing the expected response shape.
    system_prompt : str | None
        Optional system-level instruction.
    system_prompt_mode : str
        "concat" or "native".
    model : str | None
        Full model name.
    tier : str | None
        Effort level.

    Returns
    -------
    dict
        Parsed JSON object.

    Raises
    ------
    RuntimeError
        On CLI error, timeout, or JSON extraction failure.
    """
    effective_prompt, native_sp = _build_prompt(prompt, system_prompt, system_prompt_mode)
    extra = ["--json-schema", json.dumps(schema)]
    args, stdin_input = _build_args(
        effective_prompt,
        model=model,
        tier=tier,
        system_prompt_native=native_sp,
        extra_args=extra,
    )
    envelope = await _run_claude(
        args,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS,
        stdin_input=stdin_input,
    )
    result = envelope.get("structured_output")
    if result is None:
        result = envelope.get("result")
    if not isinstance(result, dict):
        raise ProviderJsonError(
            "claude",
            "CLI result was not a JSON object.",
            details=f"Got {type(result).__name__}: {result!r}",
        )
    return result
