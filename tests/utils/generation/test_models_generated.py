"""The generated menu module is current, valid, and holds the thesis defaults.

These tests are what makes the codegen design safe: a regenerated catalog that
drops a model the thesis runs on fails here instead of changing behaviour.
"""

from __future__ import annotations

from datetime import datetime

from utils.generation import DEFAULT_MODELS, DEFAULT_TIER
from utils.generation import agy, claude, codex
from utils.generation import models as menus
from utils.generation.catalog import (
    CATALOG_PATH,
    MODELS_MODULE_PATH,
    SCHEMA_PATH,
    load_catalog,
)
from utils.generation.catalog.codegen import models_module_is_current, render_models_module
from utils.generation.catalog.validate import validate_catalog


def test_committed_catalog_validates() -> None:
    validate_catalog(load_catalog(CATALOG_PATH), SCHEMA_PATH)


def test_models_module_is_rendered_from_the_committed_catalog() -> None:
    catalog = load_catalog(CATALOG_PATH)
    assert models_module_is_current(catalog, MODELS_MODULE_PATH), (
        "utils/generation/models.py is stale: run `python -m utils.generation.catalog "
        "update --render-only` and commit"
    )
    assert menus.GENERATED_AT == catalog["generated_at"]


def test_rendering_is_deterministic() -> None:
    catalog = load_catalog(CATALOG_PATH)
    assert render_models_module(catalog) == render_models_module(catalog)


def test_generated_timestamp_is_iso() -> None:
    datetime.fromisoformat(menus.GENERATED_AT.replace("Z", "+00:00"))


def test_thesis_defaults_are_in_their_menus() -> None:
    assert codex.normalize_model(DEFAULT_MODELS["codex"]) in menus.CODEX_MODELS
    assert claude.normalize_model(DEFAULT_MODELS["claude"]) in menus.CLAUDE_MODELS
    assert agy.normalize_model(DEFAULT_MODELS["agy"]) in menus.AGY_MODELS


def test_default_tier_is_valid_for_every_default_model() -> None:
    assert codex.normalize_tier(DEFAULT_TIER, DEFAULT_MODELS["codex"]) == DEFAULT_TIER
    assert claude.normalize_tier(DEFAULT_TIER) == DEFAULT_TIER
    assert agy.normalize_tier(DEFAULT_TIER, DEFAULT_MODELS["agy"]) == DEFAULT_TIER


def test_menu_constants_agree_with_catalog_rows() -> None:
    catalog = load_catalog(CATALOG_PATH)
    for name in menus.CATALOG_PROVIDERS:
        rows = catalog["providers"][name]["models"]
        assert getattr(menus, f"{name.upper()}_MODELS") == tuple(r["id"] for r in rows)
        assert getattr(menus, f"{name.upper()}_TIERS") == {r["id"]: tuple(r["tiers"]) for r in rows}
