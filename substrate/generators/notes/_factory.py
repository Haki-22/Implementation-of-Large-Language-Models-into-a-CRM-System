"""Assemble the note rows.

Draws the contact assignment, decides per note whether it carries personal data,
renders the text and stamps a timestamp inside the substrate's timeline.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from substrate.constants import SUBSTRATE_REFERENCE_DATETIME

from ._distribution import _weighted_contact_ids
from ._render import _render_note

# Fixed anchor for note timestamps so the committed snapshot is reproducible:
# the substrate's "today" (the day of the last Amazon order, see
# substrate/constants.py); every created_at is this anchor minus a seeded age of
# up to one year, so the notes sit inside the behavioural timeline.
NOTES_ANCHOR = SUBSTRATE_REFERENCE_DATETIME


# ---------------------------------------------------------------------------
# Note rows
# ---------------------------------------------------------------------------


def generate_notes(
    contacts: list[dict[str, Any]],
    *,
    seed: int = 42,
    n: int = 80,
    pii_rate: float = 0.30,
    today: datetime | None = None,
) -> list[dict[str, Any]]:
    """Generate deterministic Czech note rows for a Contact snapshot.

    Args:
        contacts: Contact snapshot rows in DB insertion order; `contact_id` is
            interpreted as 1-based list position.
        seed: RNG seed.
        n: Number of notes to generate.
        pii_rate: Approximate share of notes that embed one of the contact's
            own personal-data fields.
        today: Anchor for generated timestamps; defaults to ``NOTES_ANCHOR``.

    Returns:
        List of dicts matching the `Note` SQLModel columns.
    """
    if not 0 <= pii_rate <= 1:
        raise ValueError("pii_rate must be between 0 and 1")
    if n < 0:
        raise ValueError("n must be non-negative")

    rng = random.Random(seed)
    anchor = today or NOTES_ANCHOR
    notes: list[dict[str, Any]] = []
    contact_ids = _weighted_contact_ids(len(contacts), n, rng)

    for contact_id in contact_ids:
        contact = contacts[contact_id - 1]
        pii = rng.random() < pii_rate
        age_days = rng.randint(0, 365)
        age_minutes = rng.randint(0, 24 * 60)
        created_at = anchor - timedelta(days=age_days, minutes=age_minutes)
        category, content = _render_note(contact, rng, pii=pii)
        notes.append(
            {
                "contact_id": contact_id,
                "content": content,
                "category": category,
                "created_at": created_at.replace(microsecond=0).isoformat(),
                "pseudonymized": False,
            }
        )

    notes.sort(key=lambda row: (row["contact_id"], row["created_at"]))
    return notes
