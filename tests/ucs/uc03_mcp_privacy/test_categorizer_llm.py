"""Tests for the Claude Sonnet LLM categorizer adapter (envelope-safe).

Provider switched from Vertex Gemini → Claude Sonnet on 2026-05-31 after the
Vertex trial expired. Tests mock ``utils.generation.claude.generate_text``.
"""

from __future__ import annotations

import json
import sys
import types


def _install_fake_claude(monkeypatch, response):
    """Replace ``utils.generation.claude.generate_text`` with a stub.

    ``response`` is either a dict (which the stub serializes to JSON), a string
    (returned verbatim), or an Exception instance (which the stub raises).
    """

    captured: dict = {}

    # Resolve the real package first so its own ``from utils.generation.claude import ...``
    # is satisfied before the provider module is replaced (otherwise the order of tests
    # in a session decided whether the stub was ever reached).
    import utils.generation  # noqa: F401

    async def fake_generate_text(prompt, *, system_prompt=None, model=None, timeout=None, **kwargs):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        captured["model"] = model
        captured["kwargs"] = kwargs
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return json.dumps(response, ensure_ascii=False)
        return response

    fake_module = types.ModuleType("utils.generation.claude")
    fake_module.generate_text = fake_generate_text
    monkeypatch.setitem(sys.modules, "utils.generation.claude", fake_module)
    return captured


def test_llm_path_returns_claude_result(monkeypatch):
    from ucs.uc03_mcp_privacy import categorizer

    captured = _install_fake_claude(
        monkeypatch,
        {"category": "support", "confidence": 0.91, "reason": "warranty mentioned"},
    )

    result = categorizer.categorize_text_llm("Záruční vada notebooku.")

    assert result.category == "support"
    assert result.confidence == 0.91
    assert result.provider.startswith("claude/")
    assert "Záruční vada" in captured["prompt"]


def test_llm_path_parses_markdown_fenced_json(monkeypatch):
    """Sonnet often wraps JSON in ```json...``` fences — parser must strip them."""
    from ucs.uc03_mcp_privacy import categorizer

    _install_fake_claude(
        monkeypatch,
        '```json\n{"category": "sales", "confidence": 0.85, "reason": "sleva"}\n```',
    )

    result = categorizer.categorize_text_llm("Mám zájem o slevu.")
    assert result.category == "sales"
    assert result.confidence == 0.85


def test_llm_path_falls_back_when_dispatch_raises(monkeypatch):
    from ucs.uc03_mcp_privacy import categorizer

    _install_fake_claude(monkeypatch, RuntimeError("claude CLI not available"))

    result = categorizer.categorize_text_llm("Volal kvůli reklamaci.")

    assert result.provider == "heuristic"
    assert result.category == "complaint"


def test_llm_path_falls_back_on_invalid_enum(monkeypatch):
    from ucs.uc03_mcp_privacy import categorizer

    _install_fake_claude(
        monkeypatch,
        {"category": "definitely-not-a-real-cat", "confidence": 0.5, "reason": "garbage"},
    )

    result = categorizer.categorize_text_llm("Potřebuju support k záruce, servis nefunguje.")
    assert result.provider == "heuristic"
    assert result.category == "support"


def test_llm_path_falls_back_on_malformed_json(monkeypatch):
    from ucs.uc03_mcp_privacy import categorizer

    _install_fake_claude(monkeypatch, "not even close to JSON")

    result = categorizer.categorize_text_llm("Reklamace zásilky.")
    assert result.provider == "heuristic"


def test_dispatch_prefers_llm_when_enabled(monkeypatch):
    from ucs.uc03_mcp_privacy import categorizer

    monkeypatch.setenv("THESIS_LLM_CALLS", "TRUE")
    _install_fake_claude(
        monkeypatch,
        {"category": "sales", "confidence": 0.8, "reason": "discount"},
    )

    result = categorizer.categorize_text("Mám zájem o slevu.")
    assert result.provider.startswith("claude/")
    assert result.category == "sales"


def test_dispatch_uses_heuristic_when_llm_explicitly_disabled(monkeypatch):
    from ucs.uc03_mcp_privacy import categorizer

    monkeypatch.setenv("THESIS_LLM_CALLS", "FALSE")

    result = categorizer.categorize_text("Reklamace zásilky.")
    assert result.provider == "heuristic"
    assert result.category == "complaint"
