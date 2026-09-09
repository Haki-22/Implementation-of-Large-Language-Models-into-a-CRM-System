"""
Small public API for calling CLI-based LLM providers from project code.

Project code should call this package for all local LLM access.  The API is
intentionally small:

    await generate("Write ...")
    await generate("Return JSON ...", schema=MY_SCHEMA)
    await codex_generate("Write ...")
    await claude_generate("Write ...", model="haiku")
    await agy_generate("Write ...", model="gemini-3.1-pro", tier="high")

Default behaviour is optimized for the project's local-generation paths:
    provider = "codex"
    model    = the thesis default for that provider (DEFAULT_MODELS below)
    tier     = "low"

Provider names:
    "codex"  - OpenAI Codex CLI through the local ChatGPT account
    "claude" - Claude Code CLI through the local authenticated session
    "agy"    - Antigravity CLI (Google) through local sign-in; the standalone
               `gemini` CLI it replaced is not a provider any more
    "mock"   - deterministic offline test double

Where the model menus come from:
    Each adapter validates model ids, aliases and tiers against the generated
    module `utils/generation/models.py`, which `python -m utils.generation.catalog
    update` renders from the installed CLIs (see `utils/generation/catalog/`).
    The menus are committed code, not run-time lookups: nothing here reads the
    CLIs or the network when a call is made.  `list_options()["catalog"]` says
    which catalog generation the running code was rendered from.

Every real provider fails closed unless the global switch is on
(`THESIS_LLM_CALLS`, see `utils/llm_switch.py`); the `mock` provider is exempt.
"""

from __future__ import annotations

import importlib
import logging
import shutil
import subprocess
from typing import Any

from utils.generation import models as _menus
from utils.generation.agy import (
    AGY_MODELS,
    TIER_OPTIONS as AGY_TIERS,
)
from utils.generation.claude import (
    CLAUDE_ALIASES,
    CLAUDE_MODELS,
    TIER_OPTIONS as CLAUDE_TIERS,
)
from utils.generation.codex import (
    CODEX_MODELS,
    TIER_OPTIONS as CODEX_TIERS,
)
from utils.generation.errors import (
    GenerationError,
    LLMCallsDisabledError,
    ProviderAuthError,
    ProviderCliError,
    ProviderCliNotFoundError,
    ProviderJsonError,
    ProviderOutputError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thesis defaults (hand-written; the generated menus only validate them)
# ---------------------------------------------------------------------------

PROVIDERS: tuple[str, ...] = ("codex", "claude", "agy", "mock")
DEFAULT_PROVIDER = "codex"
DEFAULT_TIER = "low"

# What runs when a caller names no model.  Deliberately not the vendors' own
# menu defaults (those are the *_VENDOR_DEFAULT constants in models.py, e.g.
# claude-opus-5[1m]); the thesis paths want the cheaper mainstream model of
# each family.  tests/utils/generation/test_models_generated.py asserts that
# every value below still resolves into its generated menu.
DEFAULT_MODELS: dict[str, str | None] = {
    "codex": "gpt-5.6-luna",
    "claude": "sonnet",
    "agy": "gemini-3.8-flash",
    "mock": None,
}

MODEL_OPTIONS: dict[str, tuple[str, ...]] = {
    "codex": CODEX_MODELS,
    "claude": tuple(CLAUDE_ALIASES) + CLAUDE_MODELS,
    "agy": AGY_MODELS,
    "mock": ("mock",),
}

_PROVIDER_MODULES: dict[str, str] = {
    "codex": "utils.generation.codex",
    "claude": "utils.generation.claude",
    "agy": "utils.generation.agy",
    "mock": "utils.generation.mock",
}

_PROVIDER_BINARIES: dict[str, str | None] = {
    "codex": "codex",
    "claude": "claude",
    "agy": "agy",
    "mock": None,
}

# Provider names that used to exist; naming one gets a pointer, not a KeyError.
_RENAMED_PROVIDERS: dict[str, str] = {
    "gemini": "agy",
}

_NON_RETRYABLE_ERRORS = (
    LLMCallsDisabledError,
    ProviderAuthError,
    ProviderCliNotFoundError,
    ProviderQuotaError,
)


def list_options() -> dict[str, Any]:
    """
    Return the generation options exposed by the thesis API.

    Use this from CLIs or notebooks when you want to show the operator what
    provider/model/tier values are supported without opening provider files.
    The returned dict is plain data and safe to print.  ``catalog`` names the
    catalog generation the menus were rendered from.
    """
    return {
        "providers": list(PROVIDERS),
        "default_provider": DEFAULT_PROVIDER,
        "default_tier": DEFAULT_TIER,
        "default_models": dict(DEFAULT_MODELS),
        "model_options": {key: list(value) for key, value in MODEL_OPTIONS.items()},
        "tier_options": {
            "codex": list(CODEX_TIERS),
            "claude": list(CLAUDE_TIERS),
            "agy": list(AGY_TIERS),
            "mock": [],
        },
        "catalog": {
            "generated_at": _menus.GENERATED_AT,
            "providers": list(_menus.CATALOG_PROVIDERS),
            "sources": dict(_menus.SOURCES),
        },
        "cli_status": cli_status(),
    }


def cli_status() -> dict[str, dict[str, Any]]:
    """Return whether each provider CLI executable is visible on PATH."""
    status: dict[str, dict[str, Any]] = {}
    for provider in PROVIDERS:
        binary = _PROVIDER_BINARIES[provider]
        if binary is None:
            status[provider] = {
                "available": True,
                "binary": None,
                "path": None,
                "message": "Mock provider is built in and does not need an external CLI.",
            }
            continue
        path = shutil.which(binary)
        status[provider] = {
            "available": path is not None,
            "binary": binary,
            "path": path,
            "message": (
                f"`{binary}` found on PATH."
                if path is not None
                else f"CLI executable `{binary}` was not found on PATH."
            ),
        }
    return status


def cli_version(provider: str) -> str | None:
    """The version line of the provider's CLI (``<binary> --version``), for run-folder provenance.

    A run folder records which tool wrapped the model, because a provider's CLI adds
    its own system instructions and output handling; ``None`` for the mock provider or
    when the binary is missing or does not answer within 15 s.
    """
    status = cli_status().get(provider) or {}
    binary = status.get("binary")
    if not binary or not status.get("available"):
        return None
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [ln.strip() for ln in (out.stdout or out.stderr or "").splitlines() if ln.strip()]
    return lines[0][:80] if lines else None


def resolve_model(provider: str, model: str | float | None) -> str:
    """
    Return the concrete model id a call with these arguments runs on.

    ``None`` resolves to the thesis default, a Claude alias to its id, a
    tier-suffixed agy id to its base. The ``mock`` provider answers ``"mock"``.
    Callers that record provenance (the UC-01 runner) store this value, never
    the raw argument, so a run folder is self-describing even for defaults.

    Raises:
        ValueError: Unknown provider, or a model outside the generated menu.
    """
    mod = _get_provider_module(provider)
    if provider == "mock":
        return "mock"
    return mod.normalize_model(model)


def resolve_tier(provider: str, tier: str | None, model: str | float | None = None) -> str | None:
    """
    Return the reasoning tier the call will pass, validated for ``model``.

    ``None`` when the provider or the model takes no tier (``mock``, a tier-less
    agy model). Same use as ``resolve_model``.
    """
    mod = _get_provider_module(provider)
    if provider == "mock":
        return None
    return mod.normalize_tier(tier, mod.normalize_model(model))


def _get_provider_module(provider: str) -> Any:
    """
    Import the module that implements one provider.

    Args:
        provider: Provider name such as `"codex"`, `"claude"`, `"agy"`,
            or `"mock"`.

    Returns:
        The provider module.  Every provider module exposes async
        `generate_text()` and `generate_json()` functions.

    Raises:
        ValueError: If `provider` is not one of the supported provider names.
    """
    module_path = _PROVIDER_MODULES.get(provider)
    if module_path is None:
        known = ", ".join(PROVIDERS)
        if provider in _RENAMED_PROVIDERS:
            raise ValueError(
                f"Provider {provider!r} was renamed to {_RENAMED_PROVIDERS[provider]!r} "
                f"(the `gemini` CLI was retired; `agy` is Google's wrapper). Valid providers: {known}."
            )
        raise ValueError(f"Unknown provider {provider!r}. Valid providers: {known}.")
    return importlib.import_module(module_path)


async def generate(
    prompt: str,
    *,
    schema: dict[str, Any] | None = None,
    provider: str = DEFAULT_PROVIDER,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | float | None = None,
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> str | dict[str, Any]:
    """
    Generate text or JSON through one configured CLI provider.

    This is the simplest function for application code.  If `schema` is not
    provided it returns a string.  If `schema` is provided it returns a parsed
    dict that should match the JSON schema.

    Args:
        prompt: User prompt / task instructions.
        schema: Optional JSON Schema.  Pass this when you want structured
            output, for example `{"type": "object", "properties": ...}`.
        provider: Provider name.  Defaults to `"codex"` for the thesis demo.
        system_prompt: Optional higher-level instruction.  By default it is
            prepended to the prompt because that works for every provider.
        system_prompt_mode: `"concat"` works for all providers.  `"native"`
            is provider-specific (Claude only).
        model: Optional model id or alias from the provider's generated menu.
        tier: Reasoning effort.  Use `"low"` for the thesis generation paths
            unless you are deliberately running a quality comparison.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        A string for normal generation, or a dict for schema-based generation.
    """
    if schema is None:
        return await generate_text(
            prompt,
            provider=provider,
            system_prompt=system_prompt,
            system_prompt_mode=system_prompt_mode,
            model=model,
            tier=tier,
            timeout=timeout,
            retries=retries,
        )

    return await generate_json(
        prompt,
        schema,
        provider=provider,
        system_prompt=system_prompt,
        system_prompt_mode=system_prompt_mode,
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )


async def codex_generate(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | float | None = DEFAULT_MODELS["codex"],
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> str:
    """
    Generate text with Codex CLI.

    Args:
        prompt: User prompt / task instructions.
        system_prompt: Optional system instruction.
        model: Codex model id from `CODEX_MODELS`.
        tier: Codex reasoning effort from `CODEX_TIERS[model]`.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        The final text message written by Codex.
    """
    result = await generate_text(
        prompt,
        provider="codex",
        system_prompt=system_prompt,
        system_prompt_mode="concat",
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )
    return result


async def codex_generate_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    system_prompt: str | None = None,
    model: str | float | None = DEFAULT_MODELS["codex"],
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    """
    Generate a JSON object with Codex CLI and `--output-schema`.

    Args:
        prompt: User prompt / task instructions.
        schema: JSON Schema describing the expected final response.
        system_prompt: Optional system instruction, prepended to `prompt`.
        model: Codex model id from `CODEX_MODELS`.
        tier: Codex reasoning effort from `CODEX_TIERS[model]`.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        Parsed JSON object from Codex's final answer.
    """
    return await generate_json(
        prompt,
        schema,
        provider="codex",
        system_prompt=system_prompt,
        system_prompt_mode="concat",
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )


async def claude_generate(
    prompt: str,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | None = DEFAULT_MODELS["claude"],
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> str:
    """
    Generate text with Claude Code CLI.

    Args:
        prompt: User prompt / task instructions.
        system_prompt: Optional system instruction.
        system_prompt_mode: `"concat"` or `"native"`.  Native mode uses
            Claude's `--system-prompt` flag.
        model: Alias or id from the generated menu.  Examples: `"haiku"`,
            `"sonnet"`, `"opus"`, `"claude-opus-5[1m]"`.
        tier: Claude effort level: `"low"`, `"medium"`, `"high"`, `"xhigh"`,
            or `"max"`.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        The final text response from Claude.
    """
    return await generate_text(
        prompt,
        provider="claude",
        system_prompt=system_prompt,
        system_prompt_mode=system_prompt_mode,
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )


async def claude_generate_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | None = DEFAULT_MODELS["claude"],
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    """
    Generate a JSON object with Claude Code CLI and `--json-schema`.

    Args:
        prompt: User prompt / task instructions.
        schema: JSON Schema describing the expected final response.
        system_prompt: Optional system instruction.
        system_prompt_mode: `"concat"` or `"native"`.
        model: Alias or id from the generated menu.
        tier: Claude effort level.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        Parsed JSON object from Claude's structured response.
    """
    return await generate_json(
        prompt,
        schema,
        provider="claude",
        system_prompt=system_prompt,
        system_prompt_mode=system_prompt_mode,
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )


async def agy_generate(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = DEFAULT_MODELS["agy"],
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> str:
    """
    Generate text with the Antigravity CLI (`agy`).

    Args:
        prompt: User prompt / task instructions.
        system_prompt: Optional system instruction (concat mode only).
        model: Base id from `AGY_MODELS`.  Examples: `"gemini-3.8-flash"`,
            `"gemini-3.1-pro"`.  A tier-suffixed id is accepted too.
        tier: `"low"`, `"medium"` or `"high"`; ignored by tier-less models.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        The final text response.
    """
    return await generate_text(
        prompt,
        provider="agy",
        system_prompt=system_prompt,
        system_prompt_mode="concat",
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )


async def agy_generate_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    system_prompt: str | None = None,
    model: str | None = DEFAULT_MODELS["agy"],
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    """
    Generate a JSON object with the Antigravity CLI and `--json-schema`.

    Args:
        prompt: User prompt / task instructions.
        schema: JSON Schema describing the expected final response.
        system_prompt: Optional system instruction (concat mode only).
        model: Base id from `AGY_MODELS`.
        tier: `"low"`, `"medium"` or `"high"`; ignored by tier-less models.
        timeout: Optional timeout in seconds.
        retries: Number of retries after the first failed call.

    Returns:
        Parsed JSON object.
    """
    return await generate_json(
        prompt,
        schema,
        provider="agy",
        system_prompt=system_prompt,
        system_prompt_mode="concat",
        model=model,
        tier=tier,
        timeout=timeout,
        retries=retries,
    )


async def generate_text(
    prompt: str,
    *,
    provider: str = DEFAULT_PROVIDER,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | float | None = None,
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> str:
    """
    Generate a text response from an LLM provider.

    This lower-level function always returns text.  Prefer `generate()` unless
    you specifically want to make the return type obvious at the call site.

    Raises:
        ValueError: Unknown provider.
        RuntimeError: Provider failed after all retries.
    """
    mod = _get_provider_module(provider)
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            return await mod.generate_text(
                prompt,
                system_prompt=system_prompt,
                system_prompt_mode=system_prompt_mode,
                model=model,
                tier=tier,
                timeout=timeout,
            )
        except _NON_RETRYABLE_ERRORS:
            raise
        except GenerationError as exc:
            last_exc = exc
            if attempt < retries:
                logger.warning(
                    "generate_text attempt %d/%d failed for %s (%s); retrying",
                    attempt + 1,
                    retries + 1,
                    provider,
                    exc,
                )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                logger.warning(
                    "generate_text attempt %d/%d failed for %s (%s: %s); retrying",
                    attempt + 1,
                    retries + 1,
                    provider,
                    type(exc).__name__,
                    exc,
                )

    if isinstance(last_exc, GenerationError):
        raise last_exc

    raise GenerationError(
        provider,
        f"generate_text failed after {retries + 1} attempt(s).",
        details=str(last_exc),
    )


async def generate_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    provider: str = DEFAULT_PROVIDER,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | float | None = None,
    tier: str | None = DEFAULT_TIER,
    timeout: int | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    """
    Generate a parsed JSON object from an LLM provider.

    Every real provider receives the schema through its CLI flag
    (`--output-schema` for Codex, `--json-schema` for Claude and agy) and the
    returned object is checked to be a dict.

    Raises:
        ValueError: Unknown provider.
        RuntimeError: Provider failed, returned invalid JSON, or returned a
            non-object JSON value.
    """
    mod = _get_provider_module(provider)
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            result = await mod.generate_json(
                prompt,
                schema,
                system_prompt=system_prompt,
                system_prompt_mode=system_prompt_mode,
                model=model,
                tier=tier,
                timeout=timeout,
            )
            if not isinstance(result, dict):
                raise TypeError(
                    f"Provider {provider!r} returned {type(result).__name__}, expected dict"
                )
            return result
        except _NON_RETRYABLE_ERRORS:
            raise
        except GenerationError as exc:
            last_exc = exc
            if attempt < retries:
                logger.warning(
                    "generate_json attempt %d/%d failed for %s (%s); retrying",
                    attempt + 1,
                    retries + 1,
                    provider,
                    exc,
                )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                logger.warning(
                    "generate_json attempt %d/%d failed for %s (%s: %s); retrying",
                    attempt + 1,
                    retries + 1,
                    provider,
                    type(exc).__name__,
                    exc,
                )

    if isinstance(last_exc, GenerationError):
        raise last_exc

    raise GenerationError(
        provider,
        f"generate_json failed after {retries + 1} attempt(s).",
        details=str(last_exc),
    )


__all__ = [
    "cli_version",
    "DEFAULT_MODELS",
    "DEFAULT_PROVIDER",
    "DEFAULT_TIER",
    "MODEL_OPTIONS",
    "PROVIDERS",
    "GenerationError",
    "LLMCallsDisabledError",
    "ProviderAuthError",
    "ProviderCliError",
    "ProviderCliNotFoundError",
    "ProviderJsonError",
    "ProviderOutputError",
    "ProviderQuotaError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "agy_generate",
    "agy_generate_json",
    "claude_generate",
    "claude_generate_json",
    "codex_generate",
    "codex_generate_json",
    "cli_status",
    "generate",
    "generate_json",
    "generate_text",
    "list_options",
    "resolve_model",
    "resolve_tier",
]
