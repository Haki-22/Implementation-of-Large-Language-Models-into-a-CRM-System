"""Tests for Amazon reviewer lookup helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_index_by_reviewer_and_get_user():
    from substrate.pipeline.amazon_lookup import get_amazon_user, index_by_reviewer

    users = [
        {"reviewerID": "R1", "group": "A", "reviews": []},
        {"reviewerID": "R2", "group": "B", "reviews": []},
    ]
    index = index_by_reviewer(users)

    assert get_amazon_user("R1", index)["group"] == "A"
    assert get_amazon_user(None, index) is None
    assert get_amazon_user("missing", index) is None


def test_index_by_reviewer_rejects_duplicates():
    from substrate.pipeline.amazon_lookup import index_by_reviewer

    with pytest.raises(ValueError, match="duplicate reviewerID"):
        index_by_reviewer([{"reviewerID": "R1"}, {"reviewerID": "R1"}])


def test_load_index_from_mock_file(tmp_path):
    from substrate.pipeline.amazon_lookup import load_index

    path = tmp_path / "amazon.json"
    path.write_text(json.dumps([{"reviewerID": "R1", "group": "C"}]), encoding="utf-8")

    assert load_index(path)["R1"]["group"] == "C"


def test_real_snapshot_lookup_when_present():
    from substrate.pipeline.amazon_lookup import load_index

    path = Path("substrate/snapshots/amazon/amazon-original-en.json")
    if not path.exists():
        pytest.skip("real English Amazon snapshot is not present")

    index = load_index(path)

    from substrate.pipeline.data_acquisition.fetch_and_filter import STRATIFIED_TOTAL

    # Fewer reviewers than contacts on purpose: the substrate's remaining
    # contacts are prospects with no Amazon link.
    assert len(index) == STRATIFIED_TOTAL
    first = next(iter(index.values()))
    assert {"reviewerID", "group", "reviews"} <= set(first)


def test_prospects_have_no_amazon_link():
    """The substrate holds more contacts than reviewers, on purpose.

    The excess are prospects: contacts nobody has ever sold to. They are the only
    true cold-start customers available, because the Amazon 5-core source floors
    every reviewer at five reviews. They must be clean records -- a contact is
    either missing a field or missing a history, never silently both -- and they
    must have no orders at all.
    """
    import sqlite3

    from utils.paths import SUBSTRATE_DB

    if not SUBSTRATE_DB.exists():
        pytest.skip("substrate.db not built")

    con = sqlite3.connect(SUBSTRATE_DB)
    try:
        linked, prospects = con.execute(
            "SELECT SUM(reviewer_id IS NOT NULL), SUM(reviewer_id IS NULL) FROM uc_contacts"
        ).fetchone()
        defective_prospects = con.execute(
            "SELECT COUNT(*) FROM uc_contacts WHERE reviewer_id IS NULL AND is_clean = 0"
        ).fetchone()[0]
        prospect_orders = con.execute(
            "SELECT COUNT(*) FROM uc_orders o "
            "JOIN uc_contacts c ON c.id = o.contact_id WHERE c.reviewer_id IS NULL"
        ).fetchone()[0]
    finally:
        con.close()

    assert prospects > 0, "the substrate should carry contacts with no purchase history"
    assert linked + prospects == 500
    assert defective_prospects == 0, "prospects must be clean, so the two defects stay separable"
    assert prospect_orders == 0, "a prospect has never bought anything"
