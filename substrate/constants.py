"""Substrate-wide constants that every layer must agree on.

SUBSTRATE_REFERENCE_DATE
    The single "today" of the synthetic CRM. The behavioural layer keeps the real
    Amazon timestamps (orders 1999-12-01 … 2014-07-23), so anything that needs a
    "now" (age at reference, note timestamps, purchase recency) is computed from
    the day of the last order, not from the wall clock. Decision of 2026-09-02
    (substrate walkthrough): keep the real dates untouched and anchor everything
    else to them, rather than shifting the orders into the present.

NOTE_CATEGORIES
    The controlled vocabulary of ``Note.category``. Two sides enforce it — the
    substrate generator picks from it when seeding notes, UC-03's categoriser
    rejects anything outside it when writing one at run time — so it must have
    one definition and neither consumer may own it. It lives here rather than in
    ``schema/models.py`` because UC-03's MCP path reaches SQLite directly to stay
    light (10 ms to import); pulling SQLModel in for six strings would cost it
    ~180 ms. ``schema.models`` re-exports it, so it is still discoverable at the
    model.

STYLE_EXCERPT_CHARS
    Length of ``Contact.style_excerpt``, the sample of the customer's own Czech
    writing that UC-01 pastes into a prompt for style mirroring. The assembler
    cuts the longest translated review to this many characters; the prompt
    formatter must not paste more, so both read the number from here.

REVIEWS_FTS_TABLE
    Name of the SQLite FTS5 full-text index the assembler builds over the four
    text columns of ``uc_reviews``. A virtual table, so it is not an ORM entity;
    readers that open the database with plain ``sqlite3`` (UC-03's tools) need
    the name without importing SQLModel, hence it lives in this leaf.

LIFECYCLE_STAGES
    The rows of ``uc_lifecycle_stages``: code, Czech and English label, rule in
    words. ``substrate.lifecycle.classify_lifecycle`` returns the codes; the
    assembler seeds the table from this tuple at build.
"""

from __future__ import annotations

from datetime import date, datetime

SUBSTRATE_REFERENCE_DATE: date = date(2014, 7, 23)
SUBSTRATE_REFERENCE_DATETIME: datetime = datetime(2014, 7, 23, 23, 59, 59)

NOTE_CATEGORIES: tuple[str, ...] = (
    "complaint",
    "support",
    "sales",
    "follow_up",
    "delivery",
    "general",
)

STYLE_EXCERPT_CHARS: int = 600

REVIEWS_FTS_TABLE: str = "uc_reviews_fts"

# The customer lifecycle vocabulary: the rows of ``uc_lifecycle_stages``, seeded
# by the assembler. Codes are what ``Contact.lifecycle_stage`` stores and what
# ``substrate.lifecycle.classify_lifecycle`` returns; the labels are what a prompt
# or a screen shows. Thresholds after Berry & Linoff ch. 5 and Kumar & Reinartz
# section 6.1 (RFM), as fixed in UC-04's original ``rfm_lifecycle.py``.
LIFECYCLE_STAGES: tuple[dict[str, str], ...] = (
    {
        "code": "loyal_active",
        "label_cs": "dlouhodobě věrný zákazník",
        "label_en": "loyal, buying regularly",
        "rule": "last purchase within 60 days and more than one purchase a month",
    },
    {
        "code": "active",
        "label_cs": "aktivní zákazník",
        "label_en": "active",
        "rule": "last purchase within 180 days (or within 30 days at a modest rate)",
    },
    {
        "code": "at_risk",
        "label_cs": "ohrožený odchodem",
        "label_en": "at risk",
        "rule": "last purchase 180 to 365 days ago",
    },
    {
        "code": "win_back_candidate",
        "label_cs": "kandidát na návrat",
        "label_en": "win-back candidate",
        "rule": "last purchase 1 to 2 years ago, used to buy more than every other month",
    },
    {
        "code": "churned",
        "label_cs": "ztracený zákazník",
        "label_en": "churned",
        "rule": "last purchase over 2 years ago, or 1 to 2 years ago at a low rate",
    },
    {
        "code": "acquisition",
        "label_cs": "nový zákazník",
        "label_en": "newly acquired",
        "rule": "recent history too short or too sparse for any other stage",
    },
    {
        "code": "prospect",
        "label_cs": "potenciální zákazník bez nákupu",
        "label_en": "prospect, never bought",
        "rule": "no order at all",
    },
)
