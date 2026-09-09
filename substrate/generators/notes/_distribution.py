"""Decide which contacts get notes, and how many.

A flat "one note each" spread would make the CRM look nothing like a real one
and would give UC-03's per-contact lookup and search demos nothing to show. The
assignment is deliberately uneven instead: a small hot set of contacts collects
repeated notes, a warm set collects occasional ones, and most contacts have
none.
"""

from __future__ import annotations

import random


def _weighted_contact_ids(contact_count: int, note_count: int, rng: random.Random) -> list[int]:
    """Return a realistic uneven contact-id assignment for notes.

    Most contacts receive no note.  A small hot set receives repeated notes,
    so downstream search and per-contact lookup demos can show multi-note
    histories.
    """
    if contact_count <= 0:
        return []
    hot_count = max(1, min(contact_count, int(contact_count * 0.08)))
    warm_count = max(1, min(contact_count, int(contact_count * 0.25)))
    hot_ids = rng.sample(range(1, contact_count + 1), hot_count)
    warm_ids = rng.sample(range(1, contact_count + 1), warm_count)

    ids: list[int] = []
    for _ in range(note_count):
        roll = rng.random()
        if roll < 0.45:
            ids.append(rng.choice(hot_ids))
        elif roll < 0.80:
            ids.append(rng.choice(warm_ids))
        else:
            ids.append(rng.randint(1, contact_count))
    return ids
