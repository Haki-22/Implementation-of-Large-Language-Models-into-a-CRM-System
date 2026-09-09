"""Tests for Amazon raw-data acquisition helpers."""

from __future__ import annotations

import pytest

import gzip
import json


def test_load_json_gz_accepts_json_and_python_literal_lines(tmp_path):
    from substrate.pipeline.data_acquisition.fetch_and_filter import load_json_gz

    path = tmp_path / "mixed.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"asin": "JSON1", "title": "Strict JSON"}) + "\n")
        fh.write("{'asin': 'PY1', 'title': 'Python literal metadata'}\n")
        fh.write("not parseable\n")

    rows = list(load_json_gz(path))

    assert rows == [
        {"asin": "JSON1", "title": "Strict JSON"},
        {"asin": "PY1", "title": "Python literal metadata"},
    ]


import hashlib  # noqa: E402
from pathlib import Path  # noqa: E402


def test_verify_reports_missing_size_and_md5(tmp_path, monkeypatch):
    from substrate.pipeline.data_acquisition import fetch_and_filter as ff

    monkeypatch.setattr(
        ff,
        "SOURCES",
        {
            "good.gz": {
                "url": "http://x/good.gz",
                "size": 3,
                "md5": hashlib.md5(b"abc").hexdigest(),
            },
            "short.gz": {"url": "http://x/short.gz", "size": 3, "md5": "0" * 32},
            "bad.gz": {"url": "http://x/bad.gz", "size": 3, "md5": "0" * 32},
            "none.gz": {"url": "http://x/none.gz", "size": 3, "md5": "0" * 32},
        },
    )
    (tmp_path / "good.gz").write_bytes(b"abc")
    (tmp_path / "short.gz").write_bytes(b"ab")
    (tmp_path / "bad.gz").write_bytes(b"abd")

    assert ff.verify(tmp_path) == {
        "good.gz": "ok",
        "short.gz": "size-mismatch",
        "bad.gz": "md5-mismatch",
        "none.gz": "missing",
    }


def test_download_skips_verified_files_and_fetches_missing(tmp_path, monkeypatch):
    from substrate.pipeline.data_acquisition import _pinned
    from substrate.pipeline.data_acquisition import fetch_and_filter as ff

    monkeypatch.setattr(
        ff,
        "SOURCES",
        {
            "have.gz": {
                "url": "http://x/have.gz",
                "size": 3,
                "md5": hashlib.md5(b"abc").hexdigest(),
            },
            "need.gz": {
                "url": "http://x/need.gz",
                "size": 3,
                "md5": hashlib.md5(b"xyz").hexdigest(),
            },
        },
    )
    (tmp_path / "have.gz").write_bytes(b"abc")
    fetched = []

    # The transfer itself is the only thing faked; the skip/fetch decision and the
    # verification around it are the behaviour under test, and they live in _pinned.
    def fake_urlretrieve(url, dest):
        fetched.append(url)
        Path(dest).write_bytes(b"xyz")

    monkeypatch.setattr(_pinned.urllib.request, "urlretrieve", fake_urlretrieve)
    assert ff.download(tmp_path) == {"have.gz": "ok", "need.gz": "ok"}
    assert fetched == ["http://x/need.gz"]


def test_ensure_raw_inputs_fetches_only_missing_and_never_overwrites(tmp_path, monkeypatch):
    """The 'start here' check: fetch what is missing, refuse to touch a mismatching file."""
    from substrate.pipeline.data_acquisition import _pinned, inputs

    sources = {
        "have.gz": {"url": "http://x/have.gz", "size": 3, "md5": hashlib.md5(b"abc").hexdigest()},
        "need.gz": {"url": "http://x/need.gz", "size": 3, "md5": hashlib.md5(b"xyz").hexdigest()},
    }
    group = {"t": (sources, tmp_path)}
    (tmp_path / "have.gz").write_bytes(b"abc")
    fetched = []

    def fake_urlretrieve(url, dest):
        fetched.append(url)
        Path(dest).write_bytes(b"xyz")

    monkeypatch.setattr(_pinned.urllib.request, "urlretrieve", fake_urlretrieve)

    with pytest.raises(FileNotFoundError, match="t/need.gz: missing"):
        inputs.ensure_raw_inputs(download=False, inputs=group, announce=False)
    assert inputs.download_size_mb(group) == 3 / 1e6

    assert inputs.ensure_raw_inputs(inputs=group, announce=False) == {
        "t": {"have.gz": "ok", "need.gz": "ok"}
    }
    assert fetched == ["http://x/need.gz"]

    (tmp_path / "need.gz").write_bytes(b"xy")  # truncated: must not be silently replaced
    with pytest.raises(RuntimeError, match="size-mismatch"):
        inputs.ensure_raw_inputs(inputs=group, announce=False)
    assert fetched == ["http://x/need.gz"]
