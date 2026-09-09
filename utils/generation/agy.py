"""
Antigravity CLI (`agy`) provider for `utils.generation`.

This module calls the Antigravity CLI in print mode:

    agy -p <prompt> --model <model>[-<tier>] --output-format json --print-timeout <N>s

`agy` is Google's wrapper CLI (the standalone `gemini` CLI was retired for
individual accounts in June 2026). It routes every model it lists under
`agy models`, Gemini and non-Gemini alike; the ids come from the generated
menu in `utils/generation/models.py` (`AGY_MODELS`, `AGY_TIERS`).

Model options:
    Base ids from AGY_MODELS, e.g. `gemini-3.8-flash`, `gemini-3.1-pro`,
    `claude-sonnet-4-6`. A tier-suffixed id such as `gemini-3.8-flash-high`
    is accepted as well and split into base + tier (the suffix then wins over
    the `tier` argument).

Tier options:
    agy folds the reasoning tier into the model id suffix (`-low`, `-medium`,
    `-high`); the tiers each model takes are in AGY_TIERS. A model with no
    tiers (for example `claude-sonnet-4-6`) ignores the tier argument, so the
    package-wide default tier can be passed to every provider alike.

System prompts:
    agy has no per-call system-prompt flag, so only `concat` is supported.

Structured output:
    `generate_json()` passes the schema through `--json-schema` and reads the
    envelope's `structured_output` object. Envelope shape (agy 1.1.26, verified
    live 2026-09-04): `{"conversation_id", "status": "SUCCESS", "response": "<text>",
    "duration_seconds", "num_turns", "usage", and with --json-schema also
    "structured_output": {...}, "json_schema": {...}}`. `_text_from_envelope`
    still reads other key names defensively for future CLI versions.

Prompt size:
    agy print mode takes the prompt from the command line only (stdin is
    reserved for `--input-format stream-json`), so prompts above ~100 KiB fail
    with a clear error instead of `OSError: Argument list too long`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from typing import Any

from utils import llm_switch
from utils.generation.catalog import UPDATE_COMMAND
from utils.generation.errors import (
    GenerationError,
    ProviderJsonError,
    ProviderOutputError,
    ProviderTimeoutError,
    classify_cli_failure,
    cli_missing,
)
from utils.generation.models import (
    AGY_MODEL_STRING_FORMAT,
    AGY_MODELS,
    AGY_TIER_OPTIONS,
    AGY_TIERS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER_OPTIONS: tuple[str, ...] = AGY_TIER_OPTIONS
# Thesis default (the vendor's own menu default is AGY_VENDOR_DEFAULT in models.py).
# Must be a base id in AGY_MODELS; tests/utils/generation/test_models_generated.py checks.
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_TIMEOUT_SECONDS = 120
_CLI_BIN = "agy"

# Linux MAX_ARG_STRLEN is 128 KiB per single argv entry; agy has no stdin path
# for plain prompts, so above this limit the call is refused up front.
_ARGV_SINGLE_LIMIT = 100 * 1024
_TIER_SUFFIX = re.compile(r"^(?P<base>.+)-(?P<tier>low|medium|high)$")
# Envelope keys that may carry the answer text, in the order they are tried.
_TEXT_KEYS = ("response", "result", "text", "output", "content", "message")
_STRUCTURED_KEYS = ("structured_output", "structured", "json")
_OK_STATUSES = ("SUCCESS", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_prompt(prompt: str, system_prompt: str | None, mode: str) -> str:
    """Apply system_prompt_mode; agy supports "concat" only."""
    if system_prompt is None:
        return prompt
    if mode == "concat":
        return f"{system_prompt}\n\n{prompt}"
    if mode == "native":
        raise NotImplementedError(
            "agy has no per-call system-prompt flag. Use system_prompt_mode='concat' instead."
        )
    raise ValueError(f"Unknown system_prompt_mode {mode!r}. Valid values for agy: 'concat'.")


def split_model(model: str | None) -> tuple[str, str | None]:
    """Return ``(base_id, tier_from_suffix)`` for a user-supplied model value.

    ``None`` means the thesis default. ``gemini-3.8-flash-high`` splits into
    ``("gemini-3.8-flash", "high")``; a plain base id returns ``(id, None)``.

    Raises:
        ValueError: If neither the value nor its base is in the generated menu.
    """
    if model is None:
        return DEFAULT_MODEL, None
    key = str(model).strip()
    if key in AGY_MODELS:
        return key, None
    match = _TIER_SUFFIX.match(key)
    if match and match.group("base") in AGY_MODELS:
        return match.group("base"), match.group("tier")
    valid = ", ".join(AGY_MODELS)
    raise ValueError(
        f"Unsupported agy model {model!r}. Models in the generated catalog: {valid}. "
        f"If `agy models` lists it, run `{UPDATE_COMMAND}` and commit the result."
    )


def normalize_model(model: str | None) -> str:
    """Return the base model id that `--model` is built from (see `split_model`)."""
    return split_model(model)[0]


def normalize_tier(tier: str | None, model: str | None = None) -> str | None:
    """
    Validate an agy reasoning tier, per model when the model is known.

    Args:
        tier: `None`, `"low"`, `"medium"`, or `"high"`.
        model: Base model id. A model whose menu row lists no tiers ignores the
            argument and returns `None`.

    Returns:
        Normalized tier string, or `None` to omit the suffix.

    Raises:
        ValueError: If the tier is not accepted (for that model, when given).
    """
    if tier is None:
        return None
    resolved = str(tier).strip().lower()
    if model is not None:
        allowed = AGY_TIERS.get(model, ())
        if not allowed:
            logger.debug("agy model %s takes no reasoning tier; ignoring tier=%r", model, tier)
            return None
        if resolved not in allowed:
            raise ValueError(
                f"Unsupported agy tier {tier!r} for {model}. Valid tiers: {', '.join(allowed)}."
            )
        return resolved
    if resolved not in TIER_OPTIONS:
        raise ValueError(f"Unsupported agy tier {tier!r}. Valid tiers: {', '.join(TIER_OPTIONS)}.")
    return resolved


def model_string(base: str, tier: str | None) -> str:
    """Spell model + tier the way agy expects (`gemini-3.8-flash-low`)."""
    if not tier:
        return base
    return (AGY_MODEL_STRING_FORMAT or "{model}-{tier}").format(model=base, tier=tier)


def _build_args(
    prompt: str,
    *,
    model: str | None,
    tier: str | None,
    timeout: float,
    schema: dict | None = None,
) -> list[str]:
    """Build the `agy -p` argv list; the prompt travels on the command line."""
    if len(prompt) > _ARGV_SINGLE_LIMIT:
        raise GenerationError(
            "agy",
            f"Prompt is {len(prompt)} chars; agy print mode takes the prompt on the "
            f"command line only (limit {_ARGV_SINGLE_LIMIT}).",
            hint="Shorten or split the prompt, or use the codex/claude provider (both read stdin).",
        )
    base, suffix_tier = split_model(model)
    resolved_tier = normalize_tier(suffix_tier if suffix_tier is not None else tier, base)
    args = [
        _CLI_BIN,
        "-p",
        prompt,
        "--model",
        model_string(base, resolved_tier),
        "--output-format",
        "json",
        "--print-timeout",
        f"{int(timeout)}s",
    ]
    if schema is not None:
        args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    return args


async def _run_agy(args: list[str], timeout: float, *, cwd: str | None = None) -> str:
    """
    Execute one agy invocation and return raw stdout.

    Raises a typed `GenerationError` on timeout, non-zero exit, or empty output.
    """
    llm_switch.require_llm_calls("agy")
    if shutil.which(_CLI_BIN) is None:
        raise cli_missing("agy", _CLI_BIN)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # agy enforces --print-timeout itself; the outer guard only catches a
        # CLI that hangs past its own limit.
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout + 15)
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except Exception:
            pass
        raise ProviderTimeoutError(
            "agy",
            f"CLI timed out after {timeout}s.",
            hint="Try a lower tier, a simpler prompt, or a longer timeout.",
        ) from exc

    raw = (stdout_b or b"").decode(errors="replace").strip()
    stderr_text = (stderr_b or b"").decode(errors="replace").strip()

    if proc.returncode != 0:
        detail = stderr_text or raw or f"exit code {proc.returncode}"
        raise classify_cli_failure("agy", detail, exit_code=proc.returncode)
    if not raw:
        raise ProviderOutputError("agy", "CLI returned empty stdout.", details=stderr_text[:1000])
    return raw


def _text_from_envelope(raw: str) -> tuple[str, dict[str, Any] | None]:
    """
    Return ``(answer_text, envelope)`` from agy's `--output-format json` stdout.

    A JSON object whose `status` is not SUCCESS, or that carries an error
    marker, raises the classified error; the answer is the first string under
    one of `_TEXT_KEYS` (`response` for agy 1.1.26). Anything that is not a
    JSON object is returned as plain text (envelope ``None``).
    """
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None
    if not isinstance(envelope, dict):
        return raw, None
    status = str(envelope.get("status") or "")
    if envelope.get("is_error") or envelope.get("error") or status not in _OK_STATUSES:
        detail = (
            envelope.get("error") or envelope.get("response") or envelope.get("result") or envelope
        )
        raise classify_cli_failure("agy", f"status={status or '?'}: {detail}", exit_code=0)
    for key in _TEXT_KEYS:
        value = envelope.get(key)
        if isinstance(value, str):
            return value.strip(), envelope
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            return value["text"].strip(), envelope
    return raw, envelope


def _extract_json(text: str) -> dict:
    """
    Extract a JSON dict from a model text response.

    Strips markdown fences, then tries the whole text, then the outermost
    ``{...}`` block. Raises ProviderJsonError when nothing parses to a dict.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    raise ProviderJsonError(
        "agy",
        "generate_json could not extract a JSON object from the response.",
        details=f"Response ({len(text)} chars): {text[:1000]!r}",
    )


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
    Generate a text response via `agy -p ... --output-format json`.

    Parameters
    ----------
    prompt : str
        User-content text sent to the model.
    system_prompt : str | None
        Optional system-level instruction (prepended in concat mode).
    system_prompt_mode : str
        Only "concat" is supported; "native" raises NotImplementedError.
    model : str | None
        Base id from AGY_MODELS, or a tier-suffixed id. None uses DEFAULT_MODEL.
    tier : str | None
        "low" | "medium" | "high"; ignored by models that list no tiers.
    timeout : int | None
        Seconds; also passed to agy as --print-timeout.

    Returns
    -------
    str
        The answer text from the JSON envelope (or raw stdout when agy printed
        plain text).
    """
    effective_prompt = _build_prompt(prompt, system_prompt, system_prompt_mode)
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS
    args = _build_args(effective_prompt, model=model, tier=tier, timeout=effective_timeout)
    raw = await _run_agy(args, effective_timeout)
    text, _ = _text_from_envelope(raw)
    return text


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
    Generate a structured JSON response via `agy -p ... --json-schema ...`.

    The schema goes to agy's `--json-schema` flag. The result is read from a
    structured field of the envelope when agy provides one, else parsed from
    the answer text (fence-stripping, outermost-object extraction).

    Returns
    -------
    dict
        Parsed JSON object.
    """
    effective_prompt = _build_prompt(prompt, system_prompt, system_prompt_mode)
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS
    args = _build_args(
        effective_prompt, model=model, tier=tier, timeout=effective_timeout, schema=schema
    )
    raw = await _run_agy(args, effective_timeout)
    text, envelope = _text_from_envelope(raw)
    if envelope is not None:
        for key in _STRUCTURED_KEYS:
            value = envelope.get(key)
            if isinstance(value, dict):
                return value
    return _extract_json(text)
