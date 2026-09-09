"""
Codex CLI provider for `utils.generation`.

This module is the local adapter around:

    codex exec --model <model> -c model_reasoning_effort="<tier>" ...

It does not use an OpenAI API key.  It uses the locally authenticated Codex
CLI / ChatGPT account.

Model and tier options:
    The menu comes from the generated `utils/generation/models.py`
    (`CODEX_MODELS`, `CODEX_TIERS`), which mirrors `~/.codex/models_cache.json`
    at catalog time. An id outside the menu is refused with a hint to run
    `python -m utils.generation.catalog update`. Tiers are validated per model
    (`gpt-5.5` takes low..xhigh, `gpt-5.6-sol` also max and ultra). The thesis
    default is DEFAULT_MODEL below; the vendor's own menu default is
    `CODEX_VENDOR_DEFAULT`.

System prompts:
    Codex has no native per-call system-prompt flag.  The public API therefore
    supports system_prompt_mode="concat" only for Codex, which prepends the
    system prompt to the user prompt.

Structured output:
    `generate_json()` writes the JSON Schema to a temporary file and passes it
    to Codex through --output-schema.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path

from utils import llm_switch
from utils.generation.catalog import UPDATE_COMMAND
from utils.generation.errors import (
    ProviderJsonError,
    ProviderOutputError,
    ProviderTimeoutError,
    classify_cli_failure,
    cli_missing,
)
from utils.generation.models import (
    CODEX_MIGRATIONS,
    CODEX_MODELS,
    CODEX_TIER_OPTIONS,
    CODEX_TIERS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER_OPTIONS: tuple[str, ...] = CODEX_TIER_OPTIONS
# Thesis default (the vendor's menu default is CODEX_VENDOR_DEFAULT in models.py).
# Must be in CODEX_MODELS; tests/utils/generation/test_models_generated.py checks.
DEFAULT_MODEL = (
    "gpt-5.6-luna"  # keep equal to DEFAULT_MODELS["codex"] in __init__.py (a test checks)
)
DEFAULT_TIMEOUT_SECONDS = 120  # Codex reasoning can be slower than Claude
_CLI_BIN = "codex"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_prompt(prompt: str, system_prompt: str | None, mode: str) -> str:
    """
    Apply system_prompt_mode and return the effective prompt string.

    "concat" -- prepend system text to the user prompt.
    "native" -- raises NotImplementedError (see module docstring).
    """
    if system_prompt is None:
        return prompt
    if mode == "concat":
        return f"{system_prompt}\n\n{prompt}"
    if mode == "native":
        raise NotImplementedError(
            "Codex does not support a per-call system-prompt flag. "
            "Use system_prompt_mode='concat' instead."
        )
    raise ValueError(f"Unknown system_prompt_mode {mode!r}. Valid values for Codex: 'concat'.")


def normalize_model(model: str | float | None) -> str:
    """
    Return the full Codex model name for a user-supplied model value.

    Args:
        model: `None` (thesis default) or a model id from the generated menu,
            such as `"gpt-5.5"`.

    Returns:
        Full model name to pass to `codex exec --model`.

    Raises:
        ValueError: If the model is not in `CODEX_MODELS`.
    """
    if model is None:
        return DEFAULT_MODEL

    key = str(model).strip()
    if key in CODEX_MODELS:
        if key in CODEX_MIGRATIONS:
            logger.warning(
                "Codex announces a migration for %s -> %s; the run still uses %s",
                key,
                CODEX_MIGRATIONS[key],
                key,
            )
        return key

    valid = ", ".join(CODEX_MODELS)
    raise ValueError(
        f"Unsupported Codex model {model!r}. Models in the generated catalog: {valid}. "
        f"If the Codex CLI serves it, run `{UPDATE_COMMAND}` and commit the result."
    )


def normalize_tier(tier: str | None, model: str | None = None) -> str | None:
    """
    Validate a Codex reasoning tier, per model when the model is known.

    Args:
        tier: `None` or one of the tiers in `CODEX_TIER_OPTIONS`
            (`low`, `medium`, `high`, `xhigh`, `max`, `ultra`).
        model: Model id; when given, the tier must be in `CODEX_TIERS[model]`.

    Returns:
        Normalized tier string, or `None` to omit the override.

    Raises:
        ValueError: If the tier is not supported (by that model, when given).
    """
    if tier is None:
        return None

    resolved = str(tier).strip().lower()
    allowed = CODEX_TIERS.get(model, TIER_OPTIONS) if model is not None else TIER_OPTIONS
    if resolved not in allowed:
        valid = ", ".join(allowed)
        scope = f" for {model}" if model is not None else ""
        raise ValueError(f"Unsupported Codex tier {tier!r}{scope}. Valid tiers: {valid}.")
    return resolved


# Above this size a prompt no longer fits into one command-line argument
# (Linux caps a single argument at 128 KiB); it is passed as ``-`` and piped
# through stdin instead, which codex exec reads until EOF.
MAX_ARG_PROMPT_BYTES = 100_000


def prompt_transport(prompt: str) -> tuple[str, str | None]:
    """Return ``(positional argument, stdin text)`` for a prompt of any length."""
    if len(prompt.encode("utf-8")) > MAX_ARG_PROMPT_BYTES:
        return "-", prompt
    return prompt, None


def _build_base_args(
    prompt: str,
    *,
    model: str | float | None,
    tier: str | None,
    output_file: str,
) -> list[str]:
    """Build the base codex exec argument list (without --output-schema).

    A prompt too long for an argument becomes ``-`` here; the caller pipes the
    text (see ``prompt_transport`` and ``_run_codex``).
    """
    resolved_model = normalize_model(model)
    resolved_tier = normalize_tier(tier, resolved_model)
    args: list[str] = [
        _CLI_BIN,
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-hook-trust",
        "--sandbox",
        "danger-full-access",
        "--model",
        resolved_model,
        "--output-last-message",
        output_file,
    ]
    if resolved_tier is not None:
        args += ["-c", f'model_reasoning_effort="{resolved_tier}"']
    args.append(prompt_transport(prompt)[0])
    return args


async def _run_codex(
    args: list[str],
    output_file: str,
    timeout: float,
    stdin_text: str | None = None,
    *,
    events: list[dict] | None = None,
) -> str:
    """
    Execute a codex exec invocation and return the content of the output file.

    Progress streams to stderr (captured but not surfaced unless there is an
    error).  The final agent message is written to output_file by the CLI.
    ``stdin_text`` carries a prompt too long for an argument; it is written to
    the CLI's stdin and the pipe is closed, so the CLI sees EOF.

    Raises a typed `GenerationError` on timeout, non-zero exit, or empty output.
    """
    llm_switch.require_llm_calls("codex")
    if shutil.which(_CLI_BIN) is None:
        raise cli_missing("codex", _CLI_BIN)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            # codex exec prints "Reading additional input from stdin..." and waits
            # for EOF.  Inheriting the parent's stdin therefore hangs the call
            # whenever the parent has no terminal (background jobs, nohup, CI).
            # claude.py and gemini.py already pin DEVNULL for the same reason.
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin_text.encode("utf-8") if stdin_text is not None else None),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except Exception:
            pass
        raise ProviderTimeoutError(
            "codex",
            f"CLI timed out after {timeout}s.",
            hint="Try a lower effort tier, a simpler prompt, or a longer timeout.",
        ) from exc

    if proc.returncode != 0:
        stderr_text = (stderr_b or b"").decode(errors="replace").strip()
        raise classify_cli_failure("codex", stderr_text, exit_code=proc.returncode)

    if events is not None:
        for line in stdout_b.decode(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)

    output_path = Path(output_file)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ProviderOutputError(
            "codex",
            f"CLI produced no output in {output_file}.",
            hint="Check whether the Codex CLI completed normally and wrote a final message.",
        )

    return output_path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


async def generate_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | float | None = None,
    tier: str | None = None,
    timeout: int | None = None,
) -> str:
    """
    Generate a text response via codex exec with --output-last-message.

    Parameters
    ----------
    prompt : str
        User-content text sent to the model.
    system_prompt : str | None
        Optional system-level instruction (prepended to prompt in concat mode).
    system_prompt_mode : str
        Only "concat" is supported.  "native" raises NotImplementedError.
    model : str | float | None
        Model id from CODEX_MODELS.  Examples: "gpt-5.5", "gpt-5.6-sol".
        None uses DEFAULT_MODEL.
    tier : str | None
        Reasoning effort from CODEX_TIERS[model] ("low" for the thesis paths).
        Passed as -c model_reasoning_effort="<tier>".
        None = use ~/.codex/config.toml default.

    Returns
    -------
    str
        The model's final agent message (content of --output-last-message file).

    Raises
    ------
    RuntimeError
        On CLI error, timeout, or empty output.
    NotImplementedError
        If system_prompt_mode="native" is requested.
    """
    effective_prompt = _build_prompt(prompt, system_prompt, system_prompt_mode)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        output_file = tf.name

    try:
        args = _build_base_args(
            effective_prompt,
            model=model,
            tier=tier,
            output_file=output_file,
        )
        result = await _run_codex(
            args,
            output_file,
            timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS,
            stdin_text=prompt_transport(effective_prompt)[1],
        )
    finally:
        Path(output_file).unlink(missing_ok=True)

    return result


async def generate_json(
    prompt: str,
    schema: dict,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | float | None = None,
    tier: str | None = None,
    timeout: int | None = None,
) -> dict:
    """
    Generate a structured JSON response via --output-schema + --output-last-message.

    The schema is written to a temporary file and passed to --output-schema.
    Codex constrains its final message to the schema shape.  The output is
    captured via --output-last-message and parsed as JSON.

    Parameters
    ----------
    prompt : str
        User-content text / instruction.
    schema : dict
        JSON Schema object describing the expected response shape.
    system_prompt : str | None
        Optional system-level instruction (prepended to prompt in concat mode).
    system_prompt_mode : str
        Only "concat" is supported.  "native" raises NotImplementedError.
    model : str | float | None
        Full model name.
    tier : str | None
        Reasoning effort.  Use "low" for generation tasks.

    Returns
    -------
    dict
        Parsed JSON object matching the schema.

    Raises
    ------
    RuntimeError
        On CLI error, timeout, or JSON parse failure.
    NotImplementedError
        If system_prompt_mode="native" is requested.
    """
    effective_prompt = _build_prompt(prompt, system_prompt, system_prompt_mode)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as sf:
        json.dump(schema, sf, ensure_ascii=False)
        schema_file = sf.name

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as of:
        output_file = of.name

    try:
        args = _build_base_args(
            effective_prompt,
            model=model,
            tier=tier,
            output_file=output_file,
        )
        # Insert --output-schema before the prompt (last positional arg in args)
        prompt_arg = args.pop()
        args += ["--output-schema", schema_file, prompt_arg]

        raw = await _run_codex(
            args,
            output_file,
            timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS,
            stdin_text=prompt_transport(effective_prompt)[1],
        )
    finally:
        Path(schema_file).unlink(missing_ok=True)
        Path(output_file).unlink(missing_ok=True)

    # Strip markdown code fences defensively (Codex usually omits them with
    # --output-schema, but guard against occasional wrapping).
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderJsonError(
            "codex",
            "generate_json could not parse the final message as JSON.",
            details=f"Raw output ({len(raw)} chars): {raw[:1000]!r}",
        ) from exc

    if not isinstance(result, dict):
        raise ProviderJsonError(
            "codex",
            f"generate_json returned {type(result).__name__}, expected dict.",
            details=raw[:1000],
        )

    return result
