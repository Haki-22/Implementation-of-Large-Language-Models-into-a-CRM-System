"""Customer lifecycle stage from purchase dates: the one definition of the RFM rule.

RFM (recency, frequency, monetary) is the classic CRM segmentation (Berry &
Linoff ch. 5; Kumar & Reinartz section 6.1). The substrate reduces it to the two
inputs the source data actually supports -- how long since the last purchase and
how often the customer bought over their active span -- and maps them to one of
the six stages in ``substrate.constants.LIFECYCLE_STAGES``. No model, no
embeddings, plain arithmetic, so it runs at database build for every contact.

The thresholds were first written for UC-04's matchmaker arms. They now live
here instead: ``substrate.pipeline.build_substrate_db`` calls
``stage_from_dates`` once per contact at database build time and stores the
result in the ``lifecycle_stage`` column, and UC-04's profile-aware arms (see
``ucs.uc04_matchmaker.arms.model.rerank_als_with_profile``) simply read that
column back, so the recommendation arms and the CRM label can never disagree.
Monetary value is deliberately not an input: the substrate's
prices are a nominal conversion (see ``Product.price``) and the source has no
spend, so a "monetary" bucket would carry a claim the data cannot back.

Note on time: "recency" is measured against the substrate's one "today",
``SUBSTRATE_REFERENCE_DATE`` (the day of the last order in the source), never
the wall clock.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from substrate.constants import LIFECYCLE_STAGES

PROSPECT_STAGE = "prospect"
DAYS_PER_MONTH = 30.4

STAGE_CODES: tuple[str, ...] = tuple(stage["code"] for stage in LIFECYCLE_STAGES)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def classify_lifecycle(recency_days: float, frequency_per_month: float) -> str:
    """Map recency and frequency to a stage code (Berry-Linoff / Kumar-Reinartz thresholds).

    Args:
        recency_days: Days from the last purchase to the reference date.
        frequency_per_month: Purchases per month over the customer's active span
            (first to last purchase, floored at one month).

    Returns:
        One of the codes in ``LIFECYCLE_STAGES`` other than ``prospect``.
    """
    if recency_days > 730:
        return "churned"
    if recency_days > 365:
        return "win_back_candidate" if frequency_per_month > 0.5 else "churned"
    if recency_days > 180:
        return "at_risk"
    if recency_days > 60:
        return "active"
    if frequency_per_month > 1.0:
        return "loyal_active"
    if recency_days < 30 and frequency_per_month > 0.3:
        return "active"
    return "acquisition"


# ---------------------------------------------------------------------------
# Recency and frequency from a purchase history
# ---------------------------------------------------------------------------


def rfm_from_timestamps(timestamps: list[int], reference_ts: int) -> tuple[float, float]:
    """(recency_days, frequency_per_month) from unix purchase timestamps.

    Frequency divides the number of purchases by the active span in months,
    with the span floored at one month so a single burst does not read as a
    very high rate. Used internally by `stage_from_dates` below; this was the
    arithmetic originally written for UC-04's matchmaker before it moved here.
    """
    last_ts, first_ts = max(timestamps), min(timestamps)
    recency_days = (reference_ts - last_ts) / 86400.0
    span_months = max(last_ts - first_ts, 1) / (86400.0 * DAYS_PER_MONTH)
    frequency_per_month = len(timestamps) / max(span_months, 1.0)
    return recency_days, frequency_per_month


def stage_from_dates(order_dates: list[date], reference: date) -> str:
    """Stage code for a contact from its order dates; ``prospect`` when there are none."""
    if not order_dates:
        return PROSPECT_STAGE
    to_ts = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())  # noqa: E731
    recency_days, frequency = rfm_from_timestamps([to_ts(d) for d in order_dates], to_ts(reference))
    return classify_lifecycle(recency_days, frequency)
