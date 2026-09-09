"""Tests for the models.dev upstream fetch: corrupt-cache and atomic-write edge cases.

Covers an offline fetch against a corrupt cache (must fail cleanly, not with a
JSON decode error), a corrupt metadata file not blocking an otherwise-successful
online fetch, a crash mid-write preserving the previous cache body, and that a
successful fetch leaves no leftover ``.tmp`` files.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
import requests

from utils.generation.catalog.sources import modelsdev


class _FakeResponse:
    """A minimal stand-in for ``requests.Response`` returning an empty-but-valid catalog."""

    status_code = 200
    headers: ClassVar[dict] = {"ETag": 'W/"abc"', "Date": "Thu, 28 Aug 2026 12:00:00 GMT"}

    def raise_for_status(self):
        return None

    def json(self):
        return {"openai": {"models": {}}, "anthropic": {"models": {}}, "google": {"models": {}}}


def _offline(*args, **kwargs):
    """Stand in for ``requests.get`` when the network must appear unreachable."""
    raise requests.ConnectionError("offline")


def test_corrupt_cache_body_offline_fails_cleanly_not_with_decode_error(tmp_path, monkeypatch):
    (tmp_path / "models.dev.api.json").write_text("{truncated", encoding="utf-8")
    (tmp_path / "models.dev.meta.json").write_text(json.dumps({"etag": "x"}), encoding="utf-8")
    monkeypatch.setattr(modelsdev.requests, "get", _offline)
    with pytest.raises(RuntimeError, match="unavailable"):
        modelsdev.fetch(tmp_path)


def test_corrupt_meta_does_not_break_online_fetch(tmp_path, monkeypatch):
    (tmp_path / "models.dev.meta.json").write_text("{truncated", encoding="utf-8")
    monkeypatch.setattr(modelsdev.requests, "get", lambda *a, **k: _FakeResponse())
    result = modelsdev.fetch(tmp_path)
    assert result.status == "OK"
    assert result.source == "models.dev"


def test_failed_body_write_preserves_previous_cache(tmp_path, monkeypatch):
    from pathlib import Path

    body = tmp_path / "models.dev.api.json"
    body.write_text('{"good": true}', encoding="utf-8")
    real_write_text = Path.write_text

    def crashing_write_text(self, *args, **kwargs):
        if self.name.startswith("models.dev.api.json"):
            real_write_text(self, '{"trunc', encoding="utf-8")
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", crashing_write_text)
    monkeypatch.setattr(modelsdev.requests, "get", lambda *a, **k: _FakeResponse())
    modelsdev.fetch(tmp_path)
    assert json.loads(body.read_text(encoding="utf-8")) == {"good": True}


def test_fetch_leaves_no_partial_tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(modelsdev.requests, "get", lambda *a, **k: _FakeResponse())
    modelsdev.fetch(tmp_path)
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads((tmp_path / "models.dev.api.json").read_text(encoding="utf-8")) is not None
