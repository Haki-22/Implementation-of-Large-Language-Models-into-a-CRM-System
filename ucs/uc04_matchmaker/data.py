"""What the arena scores: customers, their purchase histories and the shop catalogue, read from ``substrate.db``.

Decision D-UC04-A (2026-09-06): UC-04 reads the CRM database like the other use
cases, not the Amazon JSON snapshots. Measured before deciding: the database and
the snapshots hold the same 425 linked customers, the same 45 951 reviews,
byte-identical Czech texts and the same hidden item for every customer; the
database adds Czech product titles, the 75 prospects and the lifecycle stage.

Leave-one-out: a customer's reviews are ordered by date, the last one is hidden
and becomes the single correct answer, the rest is the history an arm may use.
88 customers have two or more reviews on their final day; the tie is broken by
the lowest review id, which is the order the database build wrote them in.

Language branch (D-UC04-D, 2026-09-06): ``lang="cs"`` keeps the same customers,
the same histories and the same hidden items and swaps the text an arm reads: the
review text and headline for the Czech translation (empty for the 3 207 reviews the
May translation run dropped) and the product title for the Czech title
(``uc_products.name_cs``, present for 16 067 of 18 213 products; the description
stays English). Arms that read no text therefore score identically in both
branches, which is the data-integrity check; arms that read text pay the Czech tax.
Prospects (contacts without a reviewer) have no orders and therefore no history;
leave-one-out cannot score them, and they fall out of the arena by construction.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.paths import SUBSTRATE_DB

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Interaction:
    """One purchase = one review row: the product, the rating and the text an arm may read."""

    review_id: int
    asin: str
    rating: float
    date: str  # ISO day; the substrate source has day granularity
    text: str  # review text in the branch language ("" when untranslated)
    summary: str  # review headline in the branch language


@dataclass
class Customer:
    """One linked contact with its history and the hidden last purchase."""

    contact_id: int
    reviewer_id: str
    group: str  # A / B / C stratum of the substrate
    history: list[Interaction]
    held_out: Interaction
    history_asins: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Derive `history_asins` from `history` so membership checks do not rescan the list."""
        self.history_asins = {i.asin for i in self.history}


@dataclass
class Arena:
    """Everything an arm needs: the customers, the catalogue and the item index."""

    customers: list[Customer]
    catalog: dict[str, dict[str, Any]]  # asin -> title, title_cs, description, category, price
    all_asins: list[str]  # the ranking universe, sorted
    lang: str
    asin_to_idx: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Derive `asin_to_idx` from `all_asins` so a score matrix column can be found by ASIN."""
        self.asin_to_idx = {a: i for i, a in enumerate(self.all_asins)}

    @property
    def n_customers(self) -> int:
        return len(self.customers)

    @property
    def n_items(self) -> int:
        return len(self.all_asins)


# ---------------------------------------------------------------------------
# Reading the database
# ---------------------------------------------------------------------------


def connect(db_path: Path = SUBSTRATE_DB) -> sqlite3.Connection:
    """Open the substrate read-only; the arena never writes to the CRM."""
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"substrate database not found at {db_path}; build it with "
            "`python -m substrate.pipeline.build_all --from database`"
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_catalog(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """The shop catalogue keyed by ASIN (``uc_products.sku``)."""
    catalog: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT sku, name, name_cs, category, description, price FROM uc_products"
    ):
        catalog[row["sku"]] = {
            "asin": row["sku"],
            "title": row["name"] or "",
            "title_cs": row["name_cs"] or "",
            "description": row["description"] or "",
            "categories": [row["category"]] if row["category"] else [],
            "price": row["price"],
        }
    return catalog


def load_customers(
    conn: sqlite3.Connection, lang: str = "en", *, hold_out: bool = True
) -> list[Customer]:
    """One ``Customer`` per linked contact with at least two reviews, ordered by contact id.

    ``hold_out=False`` hides nothing: the history holds every purchase and ``held_out``
    only names the last one. The arena never uses it; the outputs for UC-01 do, because a
    recommendation for a real message must know everything the customer bought.
    """
    if lang not in {"en", "cs"}:
        raise ValueError(f"unsupported lang: {lang}")
    text_col, summary_col = ("text_cs", "summary_cs") if lang == "cs" else ("text_en", "summary_en")
    rows = conn.execute(
        f"""
        SELECT c.id AS contact_id, c.reviewer_id, c.amazon_group,
               r.id AS review_id, p.sku AS asin, r.rating, r.review_date,
               r.{text_col} AS text, r.{summary_col} AS summary
        FROM uc_reviews r
        JOIN uc_contacts c ON c.id = r.contact_id
        JOIN uc_products p ON p.id = r.product_id
        WHERE c.reviewer_id IS NOT NULL
        ORDER BY c.id, r.review_date, r.id
        """
    ).fetchall()
    by_contact: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        by_contact.setdefault(row["contact_id"], []).append(row)
    customers: list[Customer] = []
    for contact_id, group_rows in by_contact.items():
        if len(group_rows) < 2:
            continue  # nothing left as history once the last review is hidden
        interactions = [
            Interaction(
                review_id=r["review_id"],
                asin=r["asin"],
                rating=float(r["rating"] if r["rating"] is not None else 3.0),
                date=str(r["review_date"]),
                text=r["text"] or "",
                summary=r["summary"] or "",
            )
            for r in group_rows
        ]
        customers.append(
            Customer(
                contact_id=contact_id,
                reviewer_id=group_rows[0]["reviewer_id"],
                group=group_rows[0]["amazon_group"] or "?",
                history=interactions if not hold_out else interactions[:-1],
                held_out=interactions[-1],
            )
        )
    return customers


def load_arena(lang: str = "en", db_path: Path = SUBSTRATE_DB, *, hold_out: bool = True) -> Arena:
    """Build the arena for one language branch from the database (``hold_out`` as in ``load_customers``)."""
    conn = connect(db_path)
    try:
        catalog = load_catalog(conn)
        customers = load_customers(conn, lang, hold_out=hold_out)
    finally:
        conn.close()
    return Arena(customers=customers, catalog=catalog, all_asins=sorted(catalog), lang=lang)


__all__ = [
    "Arena",
    "Customer",
    "Interaction",
    "connect",
    "load_arena",
    "load_catalog",
    "load_customers",
]
