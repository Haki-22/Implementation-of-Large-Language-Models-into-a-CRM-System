"""
Tests for utils.generation public API using the mock provider.

These tests verify that generate_text() and generate_json() work correctly
with provider="mock" -- no subprocess is launched, no cost, fully offline.
Model and tier validation is tested against the generated menu in
utils/generation/models.py (which the catalog test keeps current).
"""

from __future__ import annotations

import pytest

from utils.generation import (
    DEFAULT_MODELS,
    DEFAULT_TIER,
    agy_generate,
    claude_generate,
    generate,
    generate_json,
    generate_text,
    list_options,
    resolve_model,
    resolve_tier,
)
from utils.generation import models as menus
from utils.generation.agy import normalize_model as normalize_agy_model
from utils.generation.claude import (
    generate_json as claude_generate_json_impl,
    normalize_model as normalize_claude_model,
    normalize_tier as normalize_claude_tier,
)
from utils.generation.codex import normalize_model, normalize_tier
from utils.generation.errors import (
    ProviderAuthError,
    ProviderQuotaError,
    ProviderRateLimitError,
    classify_cli_failure,
    cli_missing,
)


# ---------------------------------------------------------------------------
# Public option listing
# ---------------------------------------------------------------------------


def test_list_options_exposes_provider_models() -> None:
    """list_options() exposes provider/model choices for callers and CLIs."""
    options = list_options()
    assert options["providers"] == ["codex", "claude", "agy", "mock"]
    assert options["default_provider"] == "codex"
    assert DEFAULT_MODELS["codex"] in options["model_options"]["codex"]
    assert "sonnet" in options["model_options"]["claude"]
    assert DEFAULT_MODELS["agy"] in options["model_options"]["agy"]
    assert options["catalog"]["generated_at"] == menus.GENERATED_AT
    assert set(options["catalog"]["providers"]) == {"codex", "claude", "agy"}


def test_codex_tier_validation() -> None:
    """Codex tiers are validated per model against the generated menu."""
    assert normalize_tier("low") == "low"
    assert normalize_tier("HIGH") == "high"
    assert normalize_tier("xhigh", "gpt-5.5") == "xhigh"
    with pytest.raises(ValueError, match="Unsupported Codex tier"):
        normalize_tier("ultra", "gpt-5.5")
    with pytest.raises(ValueError, match="Unsupported Codex tier"):
        normalize_tier("turbo")


def test_codex_model_validation_points_at_the_catalog() -> None:
    """An id outside the generated menu is refused with the regeneration command."""
    assert normalize_model(None) == DEFAULT_MODELS["codex"]
    with pytest.raises(ValueError, match="utils.generation.catalog update"):
        normalize_model("gpt-5.2")


def test_claude_tier_validation() -> None:
    """Claude supports the wider effort ladder exposed by Claude Code."""
    assert normalize_claude_tier("low") == "low"
    assert normalize_claude_tier("XHIGH") == "xhigh"
    assert normalize_claude_tier("max") == "max"
    with pytest.raises(ValueError, match="Unsupported Claude tier"):
        normalize_claude_tier("ultra")


def test_claude_aliases_resolve_to_concrete_ids() -> None:
    """Aliases resolve through the generated alias map; run folders get the id."""
    assert normalize_claude_model(None) == menus.CLAUDE_ALIASES["sonnet"]
    assert normalize_claude_model("sonnet").startswith("claude-sonnet-")
    assert normalize_claude_model("best") in menus.CLAUDE_MODELS  # best -> fable -> id
    concrete = menus.CLAUDE_MODELS[0]
    assert normalize_claude_model(concrete) == concrete
    with pytest.raises(ValueError, match="Unsupported Claude model"):
        normalize_claude_model("claude-sonnet-4-6")  # not in the current menu


def test_agy_model_normalization() -> None:
    """agy accepts base ids and tier-suffixed ids from the menu, nothing else."""
    assert normalize_agy_model(None) == DEFAULT_MODELS["agy"]
    assert normalize_agy_model(f"{DEFAULT_MODELS['agy']}-high") == DEFAULT_MODELS["agy"]
    with pytest.raises(ValueError, match="Unsupported agy model"):
        normalize_agy_model("gemini-2.5-flash")


def test_resolve_model_and_tier_describe_what_runs() -> None:
    """Provenance helpers: defaults and aliases become concrete ids without a call."""
    assert resolve_model("codex", None) == DEFAULT_MODELS["codex"]
    assert resolve_model("claude", None) == menus.CLAUDE_ALIASES["sonnet"]
    assert resolve_model("claude", "sonnet") == menus.CLAUDE_ALIASES["sonnet"]
    assert resolve_model("agy", f"{DEFAULT_MODELS['agy']}-high") == DEFAULT_MODELS["agy"]
    assert resolve_model("mock", "anything") == "mock"
    assert resolve_tier("codex", DEFAULT_TIER, None) == DEFAULT_TIER
    assert resolve_tier("claude", "MAX") == "max"
    assert resolve_tier("mock", DEFAULT_TIER) is None
    tierless = next((m for m, t in menus.AGY_TIERS.items() if not t), None)
    if tierless is not None:
        assert resolve_tier("agy", DEFAULT_TIER, tierless) is None
    with pytest.raises(ValueError, match="Unsupported Codex model"):
        resolve_model("codex", "gpt-3")
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_model("vertex", None)


def test_cli_missing_error_has_install_hint() -> None:
    """Missing provider CLIs produce a typed, actionable error."""
    err = cli_missing("codex", "codex")
    assert "not found on PATH" in str(err)
    assert "Install" in str(err)


@pytest.mark.parametrize(
    ("text", "expected_type"),
    [
        ("401 unauthorized: please login", ProviderAuthError),
        ("insufficient_quota: billing hard limit exceeded", ProviderQuotaError),
        ("429 too many requests: rate limit exceeded", ProviderRateLimitError),
    ],
)
def test_cli_error_classification(text: str, expected_type: type[Exception]) -> None:
    """Provider stderr is classified into useful setup/runtime failures."""
    err = classify_cli_failure("codex", text, exit_code=1)
    assert isinstance(err, expected_type)
    assert text in err.details


# ---------------------------------------------------------------------------
# generate_text via mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_text_mock_returns_string() -> None:
    """generate_text(provider='mock') returns a non-empty string."""
    result = await generate_text("test prompt", provider="mock")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_generate_mock_text_helper_returns_string() -> None:
    """generate(provider='mock') is the simple text API."""
    result = await generate("test prompt", provider="mock")
    assert isinstance(result, str)
    assert result


@pytest.mark.asyncio
async def test_provider_specific_mock_helpers_can_be_imported() -> None:
    """Provider-specific helpers are available."""
    assert callable(claude_generate)
    assert callable(agy_generate)


# ---------------------------------------------------------------------------
# generate_json via mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_json_mock_returns_dict() -> None:
    """generate_json(provider='mock') returns a dict."""
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    result = await generate_json("test", schema, provider="mock")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_claude_generate_json_reads_structured_output(monkeypatch) -> None:
    """Claude Code stores schema output in structured_output, not result."""

    async def fake_run_claude(args, **kwargs):
        return {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "",
            "structured_output": {
                "prior_interactions": "E-mail: dotaz vyřešen.",
                "frequent_words": ["doručení", "objednávka", "reklamace"],
            },
        }

    monkeypatch.setattr("utils.generation.claude._run_claude", fake_run_claude)

    result = await claude_generate_json_impl(
        "test",
        {
            "type": "object",
            "properties": {
                "prior_interactions": {"type": "string"},
                "frequent_words": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["prior_interactions", "frequent_words"],
        },
        model="sonnet",
    )

    assert result["prior_interactions"] == "E-mail: dotaz vyřešen."
    assert result["frequent_words"] == ["doručení", "objednávka", "reklamace"]


@pytest.mark.asyncio
async def test_unknown_provider_raises_value_error() -> None:
    """generate_text with an unknown provider raises ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        await generate_text("p", provider="nonexistent")


@pytest.mark.asyncio
async def test_retired_gemini_provider_names_its_replacement() -> None:
    """The old provider name points at agy instead of failing as unknown."""
    with pytest.raises(ValueError, match="renamed to 'agy'"):
        await generate_text("p", provider="gemini")
