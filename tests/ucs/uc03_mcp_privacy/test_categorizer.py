"""Tests for UC-03 deterministic categorizer fallback."""

from __future__ import annotations


def test_categorize_text_matches_delivery():
    from ucs.uc03_mcp_privacy.categorizer import categorize_text

    result = categorize_text("Customer changed delivery address for shipping.")

    assert result.category == "delivery"
    assert result.confidence > 0.5
    assert result.to_dict()["provider"] == "heuristic"


def test_categorize_text_empty_is_general():
    from ucs.uc03_mcp_privacy.categorizer import categorize_text

    result = categorize_text(" ")

    assert result.category == "general"
    assert result.confidence == 0.0


def test_categorize_text_tie_breaks_deterministically():
    from ucs.uc03_mcp_privacy.categorizer import categorize_text

    result = categorize_text("refund warranty")

    assert result.category == "complaint"
