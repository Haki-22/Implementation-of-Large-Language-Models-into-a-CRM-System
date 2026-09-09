"""Tests for the vendor-disclosed Claude Code default model, parsed from the docs page.

Covers ``_resolve`` against a fixed docs-page fixture (per-account-type bullets,
the Opus 1M-context upgrade sentence, ambiguous/unknown accounts), and ``read``
combining the local account type with the docs fetch, including both SKIP paths
(no account type, docs unavailable).
"""

from pathlib import Path

from utils.generation.catalog.sources import claude_docs
from utils.generation.catalog.sources.claude_docs import _resolve

FIXTURE = Path(__file__).parent / "fixtures" / "claude-model-config.md"


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_resolve_max_gets_opus_with_1m_upgrade():
    assert _resolve(_text(), "max") == "claude-opus-5[1m]"


def test_resolve_pro_gets_plain_sonnet():
    assert _resolve(_text(), "pro") == "claude-sonnet-5"


def test_resolve_ambiguous_or_unknown_account_returns_none():
    # "enterprise" matches both the pay-as-you-go and the seats bullet.
    assert _resolve(_text(), "enterprise") is None
    assert _resolve(_text(), "made-up-tier") is None


def test_resolve_without_upgrade_sentence_stays_plain():
    text = _text().split("### Extended context")[0]
    assert _resolve(text, "max") == "claude-opus-5"


def test_read_skips_when_auth_unavailable(monkeypatch):
    monkeypatch.setattr(claude_docs, "_subscription_type", lambda binary, timeout: None)
    result = claude_docs.read()
    assert result.status == "SKIP"
    assert result.model_id is None


def test_read_combines_auth_and_docs(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_docs, "_subscription_type", lambda binary, timeout: "max")
    monkeypatch.setattr(
        claude_docs,
        "_fetch_docs",
        lambda cache, timeout: (_text(), "2026-08-29T00:00:00Z", "fetched"),
    )
    result = claude_docs.read(cache_dir=tmp_path)
    assert result.status == "OK"
    assert result.model_id == "claude-opus-5[1m]"
    assert "max" in result.message


def test_read_skips_when_docs_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_docs, "_subscription_type", lambda binary, timeout: "max")
    monkeypatch.setattr(
        claude_docs, "_fetch_docs", lambda cache, timeout: (None, None, "ConnectionError")
    )
    result = claude_docs.read(cache_dir=tmp_path)
    assert result.status == "SKIP"
