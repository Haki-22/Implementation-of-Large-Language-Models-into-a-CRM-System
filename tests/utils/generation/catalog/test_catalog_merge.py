"""Catalog assembly from the per-CLI sources (vendored from model-catalog)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from utils.generation.catalog.merge import _safe_default, build_catalog, fold_agy_ids
from utils.generation.catalog.sources.agy_models import AgyModels
from utils.generation.catalog.sources.claude_binary import ClaudeAliases
from utils.generation.catalog.sources.codex_cache import read as read_codex
from utils.generation.catalog import SCHEMA_PATH
from utils.generation.catalog.validate import validate_catalog


def overlay():
    """A minimal ``overlay.toml``-shaped dict covering all three providers."""
    return {
        "overlay": {"version": "test"},
        "providers": {
            "codex": {
                "cli": "codex",
                "binary": "codex",
                "default_model": "gpt-5.5",
                "default_tier": "medium",
                "fallback_allow": ["gpt-5.5"],
                "deny": [],
                "model_string_format": "{model} {tier}",
            },
            "claude": {
                "cli": "claude",
                "binary": "claude",
                "default_model": "haiku",
                "default_tier": "medium",
                "effort_tiers": ["low", "medium", "high", "xhigh", "max"],
                "allow": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
                "aliases": {
                    "opus": "claude-opus-4-8",
                    "sonnet": "claude-sonnet-4-6",
                    "haiku": "claude-haiku-4-5",
                    "fable": "claude-fable-5",
                    "default": "haiku",
                    "opusplan": "opus",
                },
            },
            "agy": {
                "cli": "agy",
                "binary": "agy",
                "default_model": "gemini-3.7-flash",
                "default_tier": "medium",
                "model_string_format": "{model}-{tier}",
                "fallback_allow": ["gemini-3.7-flash-high"],
            },
        },
    }


def upstream():
    """A fake ``UpstreamCatalog`` with one enrichable model per provider namespace."""
    return SimpleNamespace(
        source="models.dev",
        status="OK",
        message="mock",
        fetched_at="2026-08-25T00:00:00Z",
        etag="x",
        provider_models={
            "openai": {
                "gpt-5.5": {
                    "id": "gpt-5.5",
                    "name": "GPT-5.5",
                    "reasoning_options": [
                        {"type": "effort", "values": ["low", "medium", "high", "xhigh"]}
                    ],
                    "limit": {"context": 1000},
                }
            },
            "anthropic": {
                "claude-opus-5": {
                    "id": "claude-opus-5",
                    "name": "Claude Opus 5",
                    "limit": {"context": 200000},
                }
            },
            "google": {
                "gemini-3.7-flash": {
                    "id": "gemini-3.7-flash",
                    "name": "Gemini 3.7 Flash",
                    "limit": {"context": 1000000},
                }
            },
        },
    )


def codex_empty():
    """A fake ``CodexCache`` result for "not logged in" (no cache file, no config)."""
    return SimpleNamespace(
        status="SKIP",
        message="missing",
        models=[],
        fetched_at=None,
        client_version=None,
        etag=None,
        config_default_model=None,
        config_default_tier=None,
        migrations={},
    )


def codex_with_config_default():
    """``codex_empty`` plus a personalized ``config.toml`` default model and tier."""
    result = codex_empty()
    result.config_default_model = "gpt-9-personal"
    result.config_default_tier = "max"
    return result


def claude_aliases_ok():
    """A successful ``ClaudeAliases`` extraction with the standard family + ``best`` aliases."""
    return ClaudeAliases(
        "OK",
        "extracted",
        {
            "opus": "claude-opus-5",
            "sonnet": "claude-sonnet-5",
            "haiku": "claude-haiku-4-5",
            "fable": "claude-fable-5",
            "best": "fable",
        },
    )


def agy_ok():
    """A successful ``AgyModels`` live listing with tier-suffixed and a passthrough Claude id."""
    return AgyModels(
        "OK",
        "live",
        [
            {"id": "gemini-3.7-flash-high", "display_name": "Gemini 3.7 Flash (High)"},
            {"id": "gemini-3.7-flash-medium", "display_name": "Gemini 3.7 Flash (Medium)"},
            {"id": "gemini-3.7-flash-low", "display_name": "Gemini 3.7 Flash (Low)"},
            {"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6 (Thinking)"},
        ],
        "2026-08-25T00:00:00Z",
    )


def _row(mid):
    """A minimal, schema-complete catalog model row with id ``mid`` and no enrichment."""
    return {
        "id": mid,
        "display_name": mid,
        "aliases": [],
        "tiers": [],
        "default_tier": "",
        "context_window": None,
        "output_tokens": None,
        "knowledge": None,
        "release_date": None,
        "last_updated": None,
        "pricing": None,
        "modalities": None,
        "visible": True,
        "deprecated": False,
        "migration": None,
        "source": "t",
        "fetched_at": "",
    }


def test_schema_allows_partial_provider_set():
    catalog = {
        "schema_version": "1.0",
        "generated_at": "2026-08-25T00:00:00Z",
        "sources": {},
        "providers": {
            "claude": {
                "cli": "claude",
                "binary": "claude",
                "default_model": "m1",
                "default_tier": "",
                "tier_options": [],
                "aliases": {},
                "models": [_row("m1")],
            }
        },
    }
    validate_catalog(catalog, SCHEMA_PATH)  # must not raise


def test_codex_cache_filters_visible_models(tmp_path):
    cache = tmp_path / "models_cache.json"
    cache.write_text(
        json.dumps(
            {
                "fetched_at": "now",
                "models": [
                    {"slug": "gpt-5.5", "visibility": "list"},
                    {"slug": "hidden", "visibility": "hide"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = read_codex(cache_path=cache, config_path=tmp_path / "missing.toml")
    assert result.status == "OK"
    assert [m["slug"] for m in result.models] == ["gpt-5.5"]


def test_codex_cache_message_never_leaks_home_path(tmp_path, monkeypatch):
    # The message lands in the committed catalog's sources block: it must show
    # ~/.codex/..., never /home/<username>/... .
    from pathlib import Path

    home = tmp_path / "home"
    cache_dir = home / ".codex"
    cache_dir.mkdir(parents=True)
    cache = cache_dir / "models_cache.json"
    cache.write_text(
        json.dumps({"models": [{"slug": "gpt-5.5", "visibility": "list"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    result = read_codex(cache_path=cache, config_path=tmp_path / "missing.toml")
    assert str(home) not in result.message
    assert "~/.codex/models_cache.json" in result.message


def test_fold_agy_ids():
    rows = fold_agy_ids(
        [
            {"id": "gemini-3.1-pro-high", "display_name": "Gemini 3.1 Pro (High)"},
            {"id": "gemini-3.1-pro-low", "display_name": "Gemini 3.1 Pro (Low)"},
            {"id": "claude-opus-4-6-thinking", "display_name": "Claude Opus 4.6 (Thinking)"},
        ]
    )
    pro = next(r for r in rows if r["id"] == "gemini-3.1-pro")
    assert pro["tiers"] == ["low", "high"]
    assert pro["default_tier"] == "high"
    assert pro["display_name"] == "Gemini 3.1 Pro"
    think = next(r for r in rows if r["id"] == "claude-opus-4-6-thinking")
    assert think["tiers"] == []


def test_no_personalization():
    ov = overlay()
    catalog = build_catalog(
        ov, upstream(), codex_with_config_default(), claude_aliases_ok(), agy_ok()
    )
    assert (
        catalog["providers"]["codex"]["default_model"] == ov["providers"]["codex"]["default_model"]
    )
    assert catalog["providers"]["codex"]["default_tier"] == "medium"
    assert catalog["providers"]["claude"]["default_model"] == "haiku"


def test_claude_binary_map_overrides_overlay():
    catalog = build_catalog(overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy_ok())
    assert catalog["providers"]["claude"]["aliases"]["opus"] == "claude-opus-5"
    assert catalog["providers"]["claude"]["aliases"]["best"] == "fable"


def test_claude_overlay_fallback_when_extraction_skipped():
    catalog = build_catalog(
        overlay(), upstream(), codex_empty(), ClaudeAliases("SKIP", "not found"), agy_ok()
    )
    # overlay fallback aliases stand, including targets outside the allow list
    assert catalog["providers"]["claude"]["aliases"]["opus"] == "claude-opus-4-8"
    assert any(m["id"] == "claude-opus-4-8" for m in catalog["providers"]["claude"]["models"])


def test_agy_provider_folds_and_enriches():
    catalog = build_catalog(overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy_ok())
    agy = catalog["providers"]["agy"]
    flash = next(m for m in agy["models"] if m["id"] == "gemini-3.7-flash")
    assert flash["tiers"] == ["low", "medium", "high"]
    assert flash["context_window"] == 1000000  # enriched from models.dev google row
    assert agy["default_model"] == "gemini-3.7-flash"
    assert agy["default_tier"] == "medium"
    assert agy["model_string_format"] == "{model}-{tier}"
    assert any(m["id"] == "claude-sonnet-4-6" for m in agy["models"])  # non-Gemini routed row kept


def test_claude_default_prefers_vendor_docs():
    docs = SimpleNamespace(status="OK", message="vendor", model_id="claude-opus-5", fetched_at=None)
    catalog = build_catalog(
        overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy_ok(), docs
    )
    assert catalog["providers"]["claude"]["default_model"] == "claude-opus-5"
    assert catalog["sources"]["claude-docs"]["status"] == "OK"


def test_claude_default_falls_back_to_overlay_on_skip():
    docs = SimpleNamespace(status="SKIP", message="unavailable", model_id=None, fetched_at=None)
    catalog = build_catalog(
        overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy_ok(), docs
    )
    assert (
        catalog["providers"]["claude"]["default_model"]
        == overlay()["providers"]["claude"]["default_model"]
    )
    assert catalog["sources"]["claude-docs"]["status"] == "SKIP"


def test_codex_default_derives_from_cache_order():
    codex = codex_empty()
    codex.status = "OK"
    codex.models = [
        {
            "slug": "gpt-9-top",
            "display_name": "GPT-9 Top",
            "supported_reasoning_levels": [{"effort": "low"}],
            "default_reasoning_level": "low",
        },
        {
            "slug": "gpt-5.5",
            "display_name": "GPT-5.5",
            "supported_reasoning_levels": [{"effort": "medium"}],
            "default_reasoning_level": "medium",
        },
    ]
    catalog = build_catalog(overlay(), upstream(), codex, claude_aliases_ok(), agy_ok())
    # first cache row wins over the overlay value (vendor menu order)
    assert catalog["providers"]["codex"]["default_model"] == "gpt-9-top"


def test_agy_default_derives_from_list_order():
    agy = AgyModels(
        "OK",
        "live",
        [
            {"id": "gemini-9-pro-high", "display_name": "Gemini 9 Pro (High)"},
            {"id": "gemini-3.7-flash-low", "display_name": "Gemini 3.7 Flash (Low)"},
        ],
        "2026-08-25T00:00:00Z",
    )
    catalog = build_catalog(overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy)
    assert catalog["providers"]["agy"]["default_model"] == "gemini-9-pro"


def test_safe_default_falls_back_to_first_row():
    rows = [{"id": "m2"}, {"id": "m3"}]
    assert _safe_default("m1", {}, rows) == "m2"
    assert _safe_default("m2", {}, rows) == "m2"


def test_full_catalog_validates():
    catalog = build_catalog(overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy_ok())
    validate_catalog(catalog, SCHEMA_PATH)  # must not raise


def test_validate_rejects_missing_alias_target():
    catalog = build_catalog(overlay(), upstream(), codex_empty(), claude_aliases_ok(), agy_ok())
    catalog["providers"]["claude"]["aliases"]["broken"] = "missing-model"
    with pytest.raises(ValueError):
        validate_catalog(catalog, SCHEMA_PATH)
