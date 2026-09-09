"""Tests for the ``english`` step of build_all: stratified users -> cleaned English snapshot + translation queue."""

from __future__ import annotations

import json

import pytest


def _stratified():
    return [
        {
            "reviewerID": "R1",
            "group": "A",
            "reviews": [
                {
                    "asin": "B1",
                    "unixReviewTime": 10,
                    "overall": 4.0,
                    "helpful": [1, 1],
                    "summary": "Crisp &amp; sticky\u200b",
                    "reviewText": "Works\u00a0 fine",
                    "reviewerName": "A. Dent",
                },
                {
                    "asin": "B2",
                    "unixReviewTime": 20,
                    "overall": 5.0,
                    "helpful": [0, 0],
                    "summary": "",
                    "reviewText": "Only text",
                    "reviewerName": "A. Dent",
                },
            ],
            "products": [
                {"asin": "B1", "title": "DYMO Tape&amp;Label"},
                {"asin": "B2", "title": "Cable"},
            ],
        }
    ]


def test_build_cleans_text_and_emits_items(tmp_path):
    from substrate.pipeline.build_english_snapshot import build

    src = tmp_path / "strat.json"
    src.write_text(json.dumps(_stratified()), encoding="utf-8")
    out_users, out_items = tmp_path / "users.json", tmp_path / "items.jsonl"

    stats = build(src, out_users, out_items)

    users = json.loads(out_users.read_text(encoding="utf-8"))
    assert users[0]["reviews"][0]["summary"] == "Crisp & sticky"
    assert users[0]["reviews"][0]["reviewText"] == "Works fine"
    assert users[0]["reviews"][0]["review_id"] == "R1::B1::10"
    assert users[0]["products"][0]["title"] == "DYMO Tape&Label"
    items = [json.loads(line) for line in out_items.read_text(encoding="utf-8").splitlines()]
    ids = [i["item_id"] for i in items]
    assert ids == ["rs::R1::B1::10", "rt::R1::B1::10", "rt::R1::B2::20", "pt::B1", "pt::B2"]
    assert stats["users"] == 1 and stats["items_total"] == 5


def test_check_against_frozen_passes_and_fails(tmp_path):
    from substrate.pipeline.build_english_snapshot import build, check_against_frozen

    src = tmp_path / "strat.json"
    src.write_text(json.dumps(_stratified()), encoding="utf-8")
    out_users, out_items = tmp_path / "users.json", tmp_path / "items.jsonl"
    build(src, out_users, out_items)

    frozen = {
        iid: {"item_id": iid, "source_user_id": "R1" if "R1" in iid else None}
        for iid in ["rs::R1::B1::10", "rt::R1::B1::10", "rt::R1::B2::20", "pt::B1", "pt::B2"]
    }
    stage1 = tmp_path / "stage1.json"
    stage1.write_text(json.dumps(frozen), encoding="utf-8")
    result = check_against_frozen(out_items, stage1)
    assert result == {
        "items": 5,
        "frozen": 5,
        "missing_in_frozen": 0,
        "extra_in_frozen": 0,
        "users": 1,
    }

    frozen.pop("pt::B2")
    stage1.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing_in_frozen=1"):
        check_against_frozen(out_items, stage1)
