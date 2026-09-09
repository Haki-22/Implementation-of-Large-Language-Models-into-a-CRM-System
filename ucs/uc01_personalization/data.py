"""Everything UC-01 reads: one contact, one brief and the enrichment behind a level, from the database.

UC-01 reads ``substrate.db`` and nothing else (decision Q1, 2026-09-04): the
contact row with its prompt digests, the purchase history joined to the
catalogue, the lifecycle label, and what UC-04 produced for the contact
(recommendations, topics, aspects), all of which the substrate build put into
tables. The functions here are plain ``sqlite3`` reads, the way UC-03's tools
read the same file, so the single-call generation stays light enough for the
frontend to call live.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from utils.paths import SUBSTRATE_DB

# How many of the newest purchases the purchases slot shows.
RECENT_PURCHASES = 5


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContactRecord:
    """The contact as UC-01 sees it: identity for the greeting, digests for the levels."""

    id: int
    first_name: str
    last_name: str
    gender: str | None
    formal: bool | None
    name_vocative: str | None
    is_clean: bool
    title: str | None
    employer: str | None
    lifecycle_stage: str | None
    lifecycle_label: str | None
    frequent_words: list[str]
    style_excerpt: str | None
    prior_interactions: str | None
    ocean: dict[str, float] | None
    ocean_source: str | None
    reviewer_gender: str | None
    gender_paired: bool
    amazon_group: str | None

    def for_judge(self) -> dict[str, Any]:
        """The fields the rules judge compares the message against."""
        return {
            "name_vocative": self.name_vocative,
            "gender": self.gender,
            "formal": self.formal,
        }


@dataclass(frozen=True)
class Brief:
    """One operator-written message in its non-personalised form."""

    id: int
    title: str
    category: str | None
    default_template: str


@dataclass(frozen=True)
class Enrichment:
    """The per-level inputs a prompt may receive; ``None`` / empty means the contact lacks it."""

    frequent_words: list[str] = field(default_factory=list)
    style_excerpt: str | None = None
    purchases: list[dict[str, Any]] = field(default_factory=list)
    reviews: str | None = None
    role: str | None = None
    aspects: list[dict[str, Any]] = field(default_factory=list)
    ocean: dict[str, float] | None = None
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    topics: list[dict[str, Any]] = field(default_factory=list)
    lifecycle: str | None = None
    # The price line of level 6d, derived from the recommendations by pricing.offer.
    pricing: dict[str, Any] | None = None

    def present(self) -> set[str]:
        """Names of the slots this contact actually has data for."""
        out: set[str] = set()
        for name in (
            "frequent_words",
            "style_excerpt",
            "purchases",
            "reviews",
            "role",
            "aspects",
            "ocean",
            "recommendations",
            "topics",
            "lifecycle",
            "pricing",
        ):
            if getattr(self, name):
                out.add(name)
        return out


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def connect(db_path=SUBSTRATE_DB) -> sqlite3.Connection:
    """Open the substrate database read-only; fail with the command that builds it."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"substrate database missing: {db_path}. Build it with "
            "`python -m substrate.pipeline.build_all --force --from database`."
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def load_contact(conn: sqlite3.Connection, contact_id: int) -> ContactRecord:
    """The contact row joined to its employer and lifecycle label."""
    row = conn.execute(
        """SELECT c.*, co.name AS employer, s.label_cs AS lifecycle_label
           FROM uc_contacts c
           LEFT JOIN uc_companies co ON co.id = c.company_id
           LEFT JOIN uc_lifecycle_stages s ON s.code = c.lifecycle_stage
           WHERE c.id = ?""",
        (contact_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"contact {contact_id} does not exist")
    ocean = json.loads(row["ocean"]) if row["ocean"] not in (None, "null") else None
    return ContactRecord(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        gender=row["gender"],
        formal=None if row["formal"] is None else bool(row["formal"]),
        name_vocative=row["name_vocative"],
        is_clean=bool(row["is_clean"]),
        title=row["title"],
        employer=row["employer"],
        lifecycle_stage=row["lifecycle_stage"],
        lifecycle_label=row["lifecycle_label"],
        frequent_words=json.loads(row["frequent_words"]) if row["frequent_words"] else [],
        style_excerpt=row["style_excerpt"],
        prior_interactions=row["prior_interactions"],
        ocean=ocean,
        ocean_source=row["ocean_source"],
        reviewer_gender=row["reviewer_gender"],
        gender_paired=bool(row["gender_paired"]),
        amazon_group=row["amazon_group"],
    )


def load_brief(conn: sqlite3.Connection, brief_id: int) -> Brief:
    """One message brief by id."""
    row = conn.execute(
        "SELECT id, title, category, default_template FROM uc_message_briefs WHERE id = ?",
        (brief_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"brief {brief_id} does not exist")
    return Brief(row["id"], row["title"], row["category"], row["default_template"])


def recent_purchases(
    conn: sqlite3.Connection, contact_id: int, limit: int = RECENT_PURCHASES
) -> list[dict[str, Any]]:
    """The newest purchases with the product name (Czech where the catalogue has it) and category."""
    rows = conn.execute(
        """SELECT o.order_date, COALESCE(p.name_cs, p.name) AS name, p.category
           FROM uc_orders o JOIN uc_products p ON p.id = o.product_id
           WHERE o.contact_id = ? ORDER BY o.order_date DESC, o.id DESC LIMIT ?""",
        (contact_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recommendations(conn: sqlite3.Connection, contact_id: int) -> list[dict[str, Any]]:
    """UC-04's recommendations for the contact, best first, Czech product name where available."""
    rows = conn.execute(
        """SELECT r.rank, r.asin, r.score, r.reason_cs, COALESCE(p.name_cs, p.name, r.asin) AS name,
                  p.price
           FROM uc_recommendations r LEFT JOIN uc_products p ON p.id = r.product_id
           WHERE r.contact_id = ? ORDER BY r.rank""",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def topics(conn: sqlite3.Connection, contact_id: int) -> list[dict[str, Any]]:
    """UC-04's interest themes for the contact, heaviest first."""
    rows = conn.execute(
        "SELECT rank, label, weight, paradigm FROM uc_topics WHERE contact_id = ? ORDER BY rank",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def aspects(conn: sqlite3.Connection, contact_id: int) -> list[dict[str, Any]]:
    """UC-04's aspect preferences for the contact (empty until UC-04 produces them)."""
    rows = conn.execute(
        "SELECT aspect, sentiment, evidence FROM uc_aspects WHERE contact_id = ? ORDER BY id",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def czech_review_text(conn: sqlite3.Connection, contact_id: int, max_chars: int = 40_000) -> str:
    """All of a contact's Czech review bodies, newest first, for the style-match metric."""
    parts: list[str] = []
    total = 0
    for (body,) in conn.execute(
        "SELECT text_cs FROM uc_reviews WHERE contact_id = ? AND text_cs IS NOT NULL "
        "ORDER BY review_date DESC",
        (contact_id,),
    ):
        parts.append(body)
        total += len(body)
        if total >= max_chars:
            break
    return "\n".join(parts)


def load_enrichment(conn: sqlite3.Connection, contact: ContactRecord) -> Enrichment:
    """Every enrichment slot the database holds for the contact; the levels pick from it."""
    from ucs.uc01_personalization import pricing  # local: pricing imports nothing from here

    role = None
    if contact.title or contact.employer:
        role = ", ".join(p for p in (contact.title, contact.employer) if p)
    recs = recommendations(conn, contact.id)
    return Enrichment(
        frequent_words=list(contact.frequent_words),
        style_excerpt=contact.style_excerpt,
        purchases=recent_purchases(conn, contact.id),
        reviews=contact.prior_interactions,
        role=role,
        aspects=aspects(conn, contact.id),
        ocean=contact.ocean,
        recommendations=recs,
        topics=topics(conn, contact.id),
        lifecycle=contact.lifecycle_label,
        pricing=pricing.offer(recs),
    )
