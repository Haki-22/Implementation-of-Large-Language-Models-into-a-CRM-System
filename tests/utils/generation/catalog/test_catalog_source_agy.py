"""Tests for the agy model-listing source: the live/cache/overlay fallback chain.

Covers the JSON and TSV live-listing paths, falling back to the last-good cache
when the live call fails, falling back further to the overlay's fixed id list
when the cache is also unavailable, and that an expected CLI flag rejection
logs at INFO rather than WARNING.
"""

from __future__ import annotations

import json

from utils.generation.catalog.sources import agy_models

OVERLAY = {"providers": {"agy": {"binary": "agy", "fallback_allow": ["gemini-3.1-pro-high"]}}}
TSV = "Fetching available models...\ngemini-3.7-flash-high\tGemini 3.7 Flash (High)\n"
JSON_OUT = json.dumps([{"id": "gemini-3.7-flash-high", "name": "Gemini 3.7 Flash (High)"}])


def _raiser(message):
    def runner(args, timeout):
        raise RuntimeError(message)

    return runner


def test_live_json(tmp_path):
    res = agy_models.read(OVERLAY, cache_dir=tmp_path, runner=lambda a, t: JSON_OUT)
    assert res.status == "OK"
    assert res.models == [
        {"id": "gemini-3.7-flash-high", "display_name": "Gemini 3.7 Flash (High)"}
    ]
    assert (tmp_path / "agy.models.json").exists()


def test_live_tsv_fallback(tmp_path):
    def runner(args, timeout):
        if "--output-format" in args:
            raise RuntimeError("unknown flag")
        return TSV

    res = agy_models.read(OVERLAY, cache_dir=tmp_path, runner=runner)
    assert res.status == "OK"
    assert res.models[0]["id"] == "gemini-3.7-flash-high"
    assert res.models[0]["display_name"] == "Gemini 3.7 Flash (High)"


def test_cache_fallback(tmp_path):
    (tmp_path / "agy.models.json").write_text(
        json.dumps(
            {"fetched_at": "2026-08-01T00:00:00Z", "models": [{"id": "x", "display_name": "X"}]}
        ),
        encoding="utf-8",
    )
    res = agy_models.read(OVERLAY, cache_dir=tmp_path, runner=_raiser("no auth"))
    assert res.status == "CACHED"
    assert res.models[0]["id"] == "x"
    assert res.fetched_at == "2026-08-01T00:00:00Z"


def test_overlay_fallback(tmp_path):
    res = agy_models.read(OVERLAY, cache_dir=tmp_path, runner=_raiser("missing"))
    assert res.status == "SKIP"
    assert res.models == [{"id": "gemini-3.1-pro-high", "display_name": "gemini-3.1-pro-high"}]


def test_unsupported_json_flag_probe_logs_info_not_warning(tmp_path, caplog):
    # This agy build rejects `--output-format json`; that expected probe miss
    # must not WARN on every updater run.
    import logging

    def runner(args, timeout):
        if "--output-format" in args:
            raise RuntimeError("flags provided but not defined: -output-format")
        return "gemini-3.7-flash-low\tGemini 3.7 Flash (Low)"

    with caplog.at_level(logging.INFO, logger="catalog.agy"):
        res = agy_models.read(OVERLAY, cache_dir=tmp_path, runner=runner)
    assert res.status == "OK"
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
