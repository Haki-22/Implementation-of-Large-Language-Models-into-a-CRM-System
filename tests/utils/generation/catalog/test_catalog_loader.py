"""Read-only lookups over a catalog dict (vendored from model-catalog)."""

from __future__ import annotations

import pytest

from utils.generation.catalog import default_model, list_models, resolve_alias, tiers

CATALOG = {
    "providers": {
        "claude": {
            "default_model": "haiku",
            "aliases": {"haiku": "claude-haiku-4-5", "best": "fable", "fable": "claude-fable-5"},
            "models": [
                {"id": "claude-haiku-4-5", "aliases": ["haiku"], "tiers": ["low", "medium"]},
                {"id": "claude-fable-5", "tiers": []},
            ],
        }
    }
}


def test_loader_helpers() -> None:
    assert resolve_alias("claude", "haiku", CATALOG) == "claude-haiku-4-5"
    assert resolve_alias("claude", "best", CATALOG) == "claude-fable-5"  # chain
    assert (
        resolve_alias("claude", "claude-fable-5", CATALOG) == "claude-fable-5"
    )  # id passes through
    assert default_model("claude", CATALOG) == "claude-haiku-4-5"
    assert tiers("haiku", CATALOG) == ["low", "medium"]
    assert tiers("claude-fable-5", CATALOG) == []
    assert len(list_models("claude", CATALOG)) == 2
    with pytest.raises(KeyError):
        tiers("nope", CATALOG)
