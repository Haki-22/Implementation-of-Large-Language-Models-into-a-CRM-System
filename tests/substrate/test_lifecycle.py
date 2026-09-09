"""Tests for the lifecycle rule (substrate/lifecycle.py) and its vocabulary (constants)."""

from __future__ import annotations

from datetime import date

from substrate.constants import LIFECYCLE_STAGES
from substrate.lifecycle import (
    PROSPECT_STAGE,
    STAGE_CODES,
    classify_lifecycle,
    rfm_from_timestamps,
    stage_from_dates,
)


def test_thresholds_map_to_the_six_stages():
    assert classify_lifecycle(800, 5.0) == "churned"
    assert classify_lifecycle(500, 1.0) == "win_back_candidate"
    assert classify_lifecycle(500, 0.2) == "churned"
    assert classify_lifecycle(200, 3.0) == "at_risk"
    assert classify_lifecycle(90, 3.0) == "active"
    assert classify_lifecycle(10, 2.0) == "loyal_active"
    assert classify_lifecycle(10, 0.5) == "active"
    assert classify_lifecycle(45, 0.5) == "acquisition"


def test_every_code_the_rule_returns_is_in_the_vocabulary():
    seen = {
        classify_lifecycle(r, f) for r in (0, 10, 45, 90, 200, 500, 800) for f in (0.1, 0.5, 2.0)
    }
    assert seen <= set(STAGE_CODES)
    assert PROSPECT_STAGE in STAGE_CODES
    assert len({s["code"] for s in LIFECYCLE_STAGES}) == len(LIFECYCLE_STAGES)
    assert all(s["label_cs"] and s["label_en"] and s["rule"] for s in LIFECYCLE_STAGES)


def test_frequency_floors_the_span_at_one_month():
    # Three purchases in one week: not 12 a month, but 3 over a one-month floor.
    day = 86_400
    recency, frequency = rfm_from_timestamps([0, 2 * day, 6 * day], 6 * day + 30 * day)
    assert recency == 30
    assert frequency == 3.0


def test_stage_from_dates_and_prospect():
    today = date(2014, 7, 23)
    assert stage_from_dates([], today) == PROSPECT_STAGE
    # Weekly purchases through July 2014: recent and frequent.
    dates = [date(2014, 5, 1), date(2014, 6, 1), date(2014, 6, 15), date(2014, 7, 20)]
    assert stage_from_dates(dates, today) == "loyal_active"
    assert stage_from_dates([date(2010, 4, 5)], today) == "churned"
