"""
Opt-in live smoke tests for every model value exposed by utils.generation.

Normal pytest runs must stay offline, deterministic, and free.  These tests are
therefore skipped unless THESIS_LIVE_GENERATION=1 is set.

Examples:
    THESIS_LIVE_GENERATION=1 python -m pytest tests/utils/generation/test_live_provider_matrix.py -q
    THESIS_LIVE_GENERATION=1 THESIS_LIVE_PROVIDERS=codex python -m pytest tests/utils/generation/test_live_provider_matrix.py -q
    THESIS_LIVE_GENERATION=1 THESIS_LIVE_MODELS=default,gpt-5.4-mini,gpt-5.2 python -m pytest tests/utils/generation/test_live_provider_matrix.py -q
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from utils.generation import DEFAULT_TIER, generate_json, generate_text, list_options

if os.environ.get("THESIS_LLM_CALLS", "").strip().lower() not in {"true", "1", "yes", "on"}:
    pytest.skip(
        "live provider matrix skipped; export THESIS_LLM_CALLS=TRUE to run CLI calls",
        allow_module_level=True,
    )


def _csv_env(name: str) -> set[str] | None:
    """Return a comma-separated env var as a lowercase set, or None when unset."""
    raw = os.environ.get(name)
    if not raw:
        return None
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _provider_filter() -> set[str] | None:
    """Return the requested provider names from THESIS_LIVE_PROVIDERS."""
    return _csv_env("THESIS_LIVE_PROVIDERS")


def _model_filter() -> set[str] | None:
    """Return requested model labels from THESIS_LIVE_MODELS."""
    return _csv_env("THESIS_LIVE_MODELS")


def _append_unique(values: list[str], value: str) -> None:
    """Append value to values once while preserving order."""
    if value not in values:
        values.append(value)


def _live_model_cases() -> list[pytest.param]:
    """
    Build one test case per provider/model value exposed by list_options().

    Each provider gets a ``model=None`` case to verify its default route, then
    every listed model option is tested through the public API.  The test does
    not duplicate provider-specific constants.
    """
    options: dict[str, Any] = list_options()
    wanted_providers = _provider_filter()
    wanted_models = _model_filter()

    cases: list[pytest.param] = []
    for provider in options["providers"]:
        if provider == "mock":
            continue
        if wanted_providers is not None and provider.lower() not in wanted_providers:
            continue

        visible_values: list[str] = ["default"]
        for value in options["model_options"].get(provider, []):
            _append_unique(visible_values, value)

        for visible in visible_values:
            if wanted_models is not None and visible.lower() not in wanted_models:
                continue
            model = None if visible == "default" else visible
            cases.append(pytest.param(provider, model, id=f"{provider}:{visible}"))

    if not cases:
        raise RuntimeError(
            "THESIS_LIVE_PROVIDERS / THESIS_LIVE_MODELS filters selected no live cases"
        )
    return cases


def _live_json_cases() -> list[pytest.param]:
    """Build one default-model JSON smoke case per live provider."""
    options: dict[str, Any] = list_options()
    wanted_providers = _provider_filter()

    cases: list[pytest.param] = []
    for provider in options["providers"]:
        if provider == "mock":
            continue
        if wanted_providers is not None and provider.lower() not in wanted_providers:
            continue
        cases.append(pytest.param(provider, None, id=f"{provider}:default-json"))

    if not cases:
        raise RuntimeError("THESIS_LIVE_PROVIDERS selected no live JSON cases")
    return cases


def _tier_for(provider: str) -> str | None:
    """Return a conservative tier value for the provider under test.

    Every provider takes the package default; agy models without tiers ignore it.
    """
    return DEFAULT_TIER


def _normalize_ok_response(text: str) -> str:
    """Normalize a minimal OK response while still rejecting explanatory text."""
    return text.strip().strip("`'\". \n\t").upper()


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "model"), _live_model_cases())
async def test_live_text_generation_model_matrix(provider: str, model: str | None) -> None:
    """Every exposed provider/model value can complete one real text call."""
    result = await generate_text(
        "Reply with exactly OK and no other words.",
        provider=provider,
        model=model,
        tier=_tier_for(provider),
        retries=0,
    )

    assert isinstance(result, str)
    assert _normalize_ok_response(result) == "OK", (
        f"{provider} model={model or 'default'} did not return exactly OK. Raw response: {result!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "model"), _live_json_cases())
async def test_live_json_generation_default_models(provider: str, model: str | None) -> None:
    """Each live provider can complete one minimal structured-output call."""
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    result = await generate_json(
        'Return JSON only: {"ok": true}',
        schema,
        provider=provider,
        model=model,
        tier=_tier_for(provider),
        retries=0,
    )

    assert result.get("ok") is True
