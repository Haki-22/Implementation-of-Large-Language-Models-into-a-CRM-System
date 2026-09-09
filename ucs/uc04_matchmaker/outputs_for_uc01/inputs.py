"""What the prompts read from the database: histories with ids, Czech reviews, categories, lifecycle labels.

Everything comes from ``substrate.db`` through the arena loaded **without** the hold-out
(``data.load_arena(..., hold_out=False)``): for a message to a real customer every
purchase counts, nothing is hidden. Product titles are Czech where the catalogue has
them (16 067 of 18 213) and English otherwise, so the model reads what UC-01's Czech
message will name.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from ..data import Arena, Customer
from .prompts import HISTORY_CAP, PERSONA_REVIEW_CHARS, PERSONA_REVIEWS, REVIEW_CHARS_CAP


def title_of(catalog: dict[str, dict[str, Any]], asin: str) -> str:
    """The Czech title where the catalogue has one, else the English one, else the ASIN."""
    meta = catalog.get(asin) or {}
    return meta.get("title_cs") or meta.get("title") or asin


def lifecycle_labels(
    conn: sqlite3.Connection, contact_ids: list[int]
) -> dict[int, tuple[str | None, str | None]]:
    """Contact id -> (lifecycle code, Czech label) from the substrate's own rule."""
    if not contact_ids:
        return {}
    marks = ",".join("?" * len(contact_ids))
    rows = conn.execute(
        f"""SELECT c.id, c.lifecycle_stage, s.label_cs
            FROM uc_contacts c LEFT JOIN uc_lifecycle_stages s ON s.code = c.lifecycle_stage
            WHERE c.id IN ({marks})""",
        contact_ids,
    ).fetchall()
    return {row["id"]: (row["lifecycle_stage"], row["label_cs"]) for row in rows}


def history_lines(
    customer: Customer, catalog: dict[str, dict[str, Any]], cap: int = HISTORY_CAP
) -> tuple[list[str], dict[str, str]]:
    """The newest ``cap`` purchases as prompt lines ``H01 <date> ★<rating> <title>``, and the id -> ASIN map."""
    newest_first = sorted(customer.history, key=lambda it: (it.date, it.review_id), reverse=True)[
        :cap
    ]
    lines: list[str] = []
    id_to_asin: dict[str, str] = {}
    for n, it in enumerate(newest_first, start=1):
        hid = f"H{n:02d}"
        id_to_asin[hid] = it.asin
        lines.append(f"{hid} {it.date} ★{int(round(it.rating))} {title_of(catalog, it.asin)}")
    return lines, id_to_asin


def top_categories(
    customer: Customer, catalog: dict[str, dict[str, Any]], n: int = 3
) -> list[tuple[str, int]]:
    """The most bought categories of the customer with their counts."""
    counts: Counter[str] = Counter()
    for it in customer.history:
        for cat in (catalog.get(it.asin) or {}).get("categories") or []:
            counts[str(cat)] += 1
    return counts.most_common(n)


def mean_rating(customer: Customer) -> float:
    """The customer's mean history rating, or 3.0 (the neutral midpoint) for an empty history."""
    ratings = [it.rating for it in customer.history]
    return sum(ratings) / len(ratings) if ratings else 3.0


def czech_reviews(conn: sqlite3.Connection, contact_id: int) -> list[dict[str, Any]]:
    """The contact's Czech reviews (title, headline, body), newest first; reviews without a Czech body are skipped."""
    rows = conn.execute(
        """SELECT r.review_date, r.summary_cs, r.text_cs, COALESCE(p.name_cs, p.name, p.sku) AS title
           FROM uc_reviews r JOIN uc_products p ON p.id = r.product_id
           WHERE r.contact_id = ? AND r.text_cs IS NOT NULL AND r.text_cs <> ''
           ORDER BY r.review_date DESC, r.id DESC""",
        (contact_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def review_block(
    reviews: list[dict[str, Any]], cap_chars: int = REVIEW_CHARS_CAP
) -> tuple[str, int]:
    """The reviews as ``<title>: <headline> <body>`` lines up to ``cap_chars``; returns the block and its length."""
    lines: list[str] = []
    total = 0
    for r in reviews:
        body = " ".join((r.get("text_cs") or "").split())
        head = " ".join((r.get("summary_cs") or "").split())
        line = f"{r['title']}: {head} {body}".strip()
        if total + len(line) + 1 > cap_chars:
            line = line[: max(0, cap_chars - total - 1)]
            if line:
                lines.append(line)
            break
        lines.append(line)
        total += len(line) + 1
    block = "\n".join(lines)
    return block, len(block)


def review_samples(
    reviews: list[dict[str, Any]], n: int = PERSONA_REVIEWS, chars: int = PERSONA_REVIEW_CHARS
) -> list[tuple[str, str]]:
    """The ``n`` longest reviews, each cut to ``chars`` characters, for the persona prompt."""
    longest = sorted(reviews, key=lambda r: len(r.get("text_cs") or ""), reverse=True)[:n]
    out: list[tuple[str, str]] = []
    for r in longest:
        body = " ".join((r.get("text_cs") or "").split())[:chars]
        out.append((r["title"], body))
    return out


def customers_by_id(arena: Arena) -> dict[int, Customer]:
    """`arena`'s customers indexed by `contact_id`."""
    return {c.contact_id: c for c in arena.customers}


__all__ = [
    "czech_reviews",
    "customers_by_id",
    "history_lines",
    "lifecycle_labels",
    "mean_rating",
    "review_block",
    "review_samples",
    "title_of",
    "top_categories",
]
