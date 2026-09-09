"""Tests for the ``reviewer_gender`` step (substrate/pipeline/build_reviewer_gender.py).

The step is deterministic and offline: given names against Faker's English
name lists, self-reference cues in the English review text, a conflict stays
unknown. These pin the rules the artifact's ``_meta`` block describes.
"""

from __future__ import annotations

from substrate.pipeline.build_reviewer_gender import (
    build,
    cue_counts,
    cue_gender,
    infer_reviewer,
    name_gender,
)


def _user(rid: str, name: str | None, texts: list[str]) -> dict:
    return {
        "reviewerID": rid,
        "group": "A",
        "reviews": [
            {"reviewerName": name, "summary": "", "reviewText": t, "asin": f"B{i}"}
            for i, t in enumerate(texts)
        ],
    }


def test_name_gender_reads_the_first_given_name_only():
    assert name_gender("John Williamson") == "m"
    assert name_gender('Mary Jo Sminkey "15 years of Amazon Reviews!"') == "f"
    assert name_gender("J. Haggard") is None  # an initial is not a name
    assert name_gender("MagnumMan") is None  # a handle is not a name
    assert name_gender(None) is None


def test_unisex_names_yield_nothing():
    # Present in both Faker lists, so excluded on purpose.
    assert name_gender("Jordan Smith") is None


def test_cues_count_both_sides_and_majority_wins():
    assert cue_counts("My wife loves it. As a dad I need it.") == (2, 0)
    assert cue_counts("My husband set it up; as a mom I appreciate it.") == (0, 2)
    assert cue_gender(2, 0) == "m"
    assert cue_gender(0, 2) == "f"
    assert cue_gender(1, 1) is None
    assert cue_gender(0, 0) is None


def test_name_wins_and_a_conflict_stays_unknown():
    by_name_only = infer_reviewer(_user("R1", "Samuel Chell", ["Great cable."]))
    assert (by_name_only["name_gender"], by_name_only["cue_gender"], by_name_only["gender"]) == (
        "m",
        None,
        "m",
    )

    by_cue_only = infer_reviewer(_user("R2", "Spudman", ["My husband loves it."]))
    assert (by_cue_only["name_gender"], by_cue_only["cue_gender"], by_cue_only["gender"]) == (
        None,
        "f",
        "f",
    )

    conflict = infer_reviewer(_user("R3", "Mary Paschke", ["My wife loves it."]))
    assert conflict["conflict"] is True
    assert conflict["gender"] is None


def test_build_reports_the_counts_it_measured():
    users = [
        _user("R1", "Samuel Chell", ["Great cable."]),
        _user("R2", "Spudman", ["My husband loves it."]),
        _user("R3", "Mary Paschke", ["My wife loves it."]),
        _user("R4", None, ["Nothing personal here."]),
    ]
    artifact = build(users)
    meta = artifact["_meta"]
    assert meta["reviewers"] == 4
    assert meta["with_name"] == 3
    assert meta["name_verdicts"] == 2
    assert meta["cue_verdicts"] == 2
    assert (meta["both_known"], meta["both_agree"], meta["conflicts"]) == (1, 0, 1)
    assert meta["gender_counts"] == {"m": 1, "f": 1, "unknown": 2}
    assert list(artifact["reviewers"]) == ["R1", "R2", "R3", "R4"]
