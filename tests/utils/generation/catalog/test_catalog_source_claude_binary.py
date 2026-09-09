"""Tests for extracting the Claude Code alias map from the installed binary.

Covers extracting a well-formed payload, falling back to SKIP when no payload
is found or the binary is missing, and that extraction still works when the
payload straddles a chunk boundary during the streamed scan.
"""

from __future__ import annotations

from utils.generation.catalog.sources import claude_binary

PAYLOAD = (
    b'junk aliases:{opus:{default:"claude-opus-5",per_provider:{foundry:"claude-opus-4-6"}},'
    b'sonnet:{default:"claude-sonnet-5"},haiku:{default:"claude-haiku-4-5"},'
    b'fable:{default:"claude-fable-5"}},best:"fable" more junk'
)


def test_extracts_map(tmp_path):
    p = tmp_path / "claude.bin"
    p.write_bytes(b"x" * 10 + PAYLOAD + b"y" * 10)
    res = claude_binary.read(path=p)
    assert res.status == "OK"
    assert res.aliases == {
        "opus": "claude-opus-5",
        "sonnet": "claude-sonnet-5",
        "haiku": "claude-haiku-4-5",
        "fable": "claude-fable-5",
        "best": "fable",
    }


def test_no_match_falls_back(tmp_path):
    p = tmp_path / "claude.bin"
    p.write_bytes(b"nothing here")
    res = claude_binary.read(path=p)
    assert res.status == "SKIP"
    assert res.aliases == {}


def test_missing_binary():
    res = claude_binary.read(binary="definitely-not-a-cli-9x")
    assert res.status == "SKIP"


def test_payload_split_across_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_binary, "CHUNK", 64)
    monkeypatch.setattr(claude_binary, "OVERLAP", 48)
    p = tmp_path / "claude.bin"
    p.write_bytes(b"z" * 50 + PAYLOAD + b"z" * 50)
    res = claude_binary.read(path=p)
    assert res.status == "OK"
    assert res.aliases["opus"] == "claude-opus-5"
