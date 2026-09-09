"""The update command: change detection, KEPT rows for absent CLIs, codegen, check."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from utils.generation.catalog import CATALOG_PATH, SCHEMA_PATH, load_catalog
from utils.generation.catalog.__main__ import (
    _changed_count,
    _require_providers,
    _same_catalog_ignoring_audit_timestamps,
    check,
    freshness_lines,
    keep_or_drop_uninstalled,
)
from utils.generation.catalog.codegen import (
    models_module_is_current,
    render_models_module,
    write_models_module,
)
from utils.generation.catalog.validate import validate_catalog


def test_audit_only_changes_are_not_semantic():
    old = {
        "schema_version": "1.0",
        "generated_at": "2026-08-25T15:22:22Z",
        "sources": {"models.dev": {"status": "OK", "message": "fetched", "etag": "a"}},
        "providers": {"agy": {"models": [{"id": "m", "fetched_at": "2026-08-25T15:22:22Z"}]}},
    }
    new = {
        "schema_version": "1.0",
        "generated_at": "2026-08-25T15:23:00Z",
        "sources": {"models.dev": {"status": "OK", "message": "304 not-modified", "etag": "b"}},
        "providers": {"agy": {"models": [{"id": "m", "fetched_at": "2026-08-25T15:23:00Z"}]}},
    }
    assert _same_catalog_ignoring_audit_timestamps(json.dumps(old), new)
    new_real = json.loads(json.dumps(new))
    new_real["providers"]["agy"]["models"][0]["id"] = "m2"
    assert not _same_catalog_ignoring_audit_timestamps(json.dumps(old), new_real)


def test_changed_count_ignores_audit_only_row_diffs():
    old = json.dumps(
        {
            "providers": {
                "agy": {
                    "models": [{"id": "m", "tiers": ["low"], "fetched_at": "x", "source": "agy-ok"}]
                }
            }
        }
    )
    new = {
        "providers": {
            "agy": {
                "models": [{"id": "m", "tiers": ["low"], "fetched_at": "y", "source": "agy-cached"}]
            }
        }
    }
    assert _changed_count(old, new) == 0
    new["providers"]["agy"]["models"][0]["tiers"] = ["low", "high"]
    assert _changed_count(old, new) == 1


def test_missing_all_clis_raises_a_clear_error():
    _require_providers(["codex"])
    with pytest.raises(RuntimeError, match="no supported CLIs"):
        _require_providers([])


def test_freshness_warns_after_14_days():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    lines = freshness_lines(
        {
            "codex cache": "2026-08-01T00:00:00Z",
            "models.dev": "2026-08-24T00:00:00Z",
            "agy models": None,
        },
        now,
    )
    levels = {text.split(":")[0]: level for level, text in lines}
    assert levels == {"codex cache": "WARN", "models.dev": "INFO", "agy models": "INFO"}


def test_absent_cli_keeps_committed_rows_instead_of_dropping():
    """Regenerating on a machine without agy must not erase agy from the repo."""
    fresh = {
        "sources": {"agy": {"status": "SKIP", "message": "overlay fallback"}},
        "providers": {
            "codex": {"binary": "codex", "models": [{"id": "gpt-x"}]},
            "agy": {"binary": "agy", "models": [{"id": "fallback-only"}]},
            "claude": {"binary": "claude", "models": [{"id": "claude-x"}]},
        },
    }
    previous = {
        "generated_at": "2026-09-01T00:00:00Z",
        "providers": {"agy": {"binary": "agy", "models": [{"id": "gemini-committed"}]}},
    }
    installed = {"codex": True, "agy": False, "claude": False}
    present, kept, absent = keep_or_drop_uninstalled(fresh, previous, installed)
    assert present == ["codex", "agy"]
    assert kept == ["agy"]
    assert absent == ["claude"]  # never catalogued -> dropped
    assert fresh["providers"]["agy"]["models"] == [{"id": "gemini-committed"}]
    assert fresh["sources"]["agy"]["status"] == "KEPT"
    assert "2026-09-01" in fresh["sources"]["agy"]["message"]
    assert "claude" not in fresh["providers"]


def test_codegen_roundtrip_and_check(tmp_path):
    catalog = load_catalog(CATALOG_PATH)
    validate_catalog(catalog, SCHEMA_PATH)
    target = tmp_path / "models.py"
    assert write_models_module(catalog, target) is True
    assert write_models_module(catalog, target) is False  # unchanged -> no rewrite
    assert models_module_is_current(catalog, target)
    text = target.read_text(encoding="utf-8")
    assert text == render_models_module(catalog)
    assert "GENERATED, do not edit" in text
    namespace: dict = {}
    exec(compile(text, str(target), "exec"), namespace)  # the module must import cleanly
    for name in catalog["providers"]:
        assert namespace[f"{name.upper()}_MODELS"] == tuple(
            r["id"] for r in catalog["providers"][name]["models"]
        )
    assert check(CATALOG_PATH, SCHEMA_PATH, target) == 0
    target.write_text(text + "# drift\n", encoding="utf-8")
    assert check(CATALOG_PATH, SCHEMA_PATH, target) == 1
