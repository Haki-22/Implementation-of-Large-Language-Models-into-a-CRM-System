"""The picker: who the reported runs are generated for, chosen by a rule and written down.

Nobody will receive these messages, so the evidence a reader can weigh is the
text itself: the same person, the same brief, one message per level, read
side by side. That calls for a reading set, not a census. The rule (user
2026-09-04, revised 2026-09-05 and 2026-09-07, D-UC01-6): four contacts per
cell of formality x gender: **three linked contacts** (a clean row with Czech
text and a purchase history; the OCEAN profile is inferred for every linked
contact and UC-04 writes its outputs for whoever is picked, so every linked
contact can run every level) and **one prospect** with no history at all (the
behaviour levels skip; the reader sees what a mail merge and morphology alone
give). The data tiers full / partial of 2026-09-04 are gone: withholding data
from a "partial" contact only repeated a lower rung of a full one, and the two
states the database really has are *has a history* and *has none*. Within a
kind: a matching-gender history first, then the lowest contact id; prospects
by id — deterministic, no random draw. One stratum sits beside the cells: the
defective rows (no stored greeting, unknown gender or formality), which run
every level with what they have while the judge checks only what is stored.

The briefs are named, not "the lowest id of a category": one brief per
category in ``LADDER_BRIEFS``, chosen so that every enrichment has a place (a
recommendation and its price in the upsell, a lifecycle stage in the follow-up,
one's own words in the invitation).

The pick is a committed file under ``snapshots/picks/``: the rule in words, the
counts, the ids, and per contact the facts a results table may split on. Every
run copies the pick it used into its own folder. Anyone can generate for any
other contact with ``python -m ucs.uc01_personalization generate --contact N``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ucs.uc01_personalization import data, levels
from utils.file_safety import require_can_write
from utils.paths import UC01_PICKS_DIR

DEFAULT_PICK = "uc01-personalization-20-level"
PER_CELL = 4
STRATUM_SIZE = 4

# The brief the ladder runs on per category (user 2026-09-07): named, so that a
# new brief in the corpus cannot silently change what the levels are read on.
# Invitation: a sale launch leaves room for one's own words and a role. Upsell:
# a "picked for you" message is what the recommendation levels (6a, 6b, 6d)
# actually say. Follow-up: a review request refers to the last purchase, which
# the substrate holds, unlike a cart it does not.
LADDER_BRIEFS: dict[str, str] = {
    "invitation": "seasonal_sale_launch",
    "upsell": "personal_recommendation",
    "followup": "review_request_with_reward",
}
BRIEF_CATEGORIES = tuple(LADDER_BRIEFS)

# Which brief kinds each rung runs on (user 2026-09-05, D-UC01-3). The evidence
# per rung is a diff: the same contact, the same brief, one more field. The tiers
# the assignment names (L2 morphology, L3 behaviour, L5 psychographic, L6 hyper)
# run on every category, so the ladder reads top to bottom on the same three
# briefs; each single-field arm runs on the one brief where its field has a
# place (a purchase shows in an upsell, a lifecycle stage in a follow-up, one's
# own words in an invitation), which keeps the run and the reading pass small
# without losing a rung's comparison. L0 and L1 cost nothing and ride along.
LEVEL_BRIEF_CATEGORIES: dict[str, tuple[str, ...]] = {
    "0": BRIEF_CATEGORIES,
    "1": BRIEF_CATEGORIES,
    "2": BRIEF_CATEGORIES,
    "3a": ("invitation",),
    "3b": ("upsell",),
    "3c": ("upsell",),
    "3d": ("invitation",),
    "3": BRIEF_CATEGORIES,
    "4": ("upsell",),
    "5": BRIEF_CATEGORIES,
    "6a": ("upsell",),
    "6b": ("upsell",),
    "6c": ("followup",),
    "6d": ("upsell",),
    "6": BRIEF_CATEGORIES,
}

# The slots of a cell are filled in this order, cycling when per_cell is larger:
# 4 slots -> 3 linked, 1 prospect; 1 slot -> linked only.
TIER_MIX: tuple[str, ...] = ("linked", "linked", "linked", "prospect")

_CLEAN_WITH_HISTORY = (
    "c.is_clean = 1 AND c.style_excerpt IS NOT NULL "
    "AND EXISTS (SELECT 1 FROM uc_orders o WHERE o.contact_id = c.id)"
)

# The two kinds a cell mixes; they are disjoint by construction.
TIERS: dict[str, str] = {
    # a reviewer behind the row: Czech text and purchases, so every model level can run
    # (the OCEAN profile is inferred for every linked contact; UC-04 writes for the pick)
    "linked": _CLEAN_WITH_HISTORY,
    # no reviewer at all: no text and no purchases, so L3 and above skip
    "prospect": "c.is_clean = 1 AND c.reviewer_id IS NULL",
}
_ORDER = "ORDER BY c.gender_paired DESC, c.id"

RULE = (
    "per cell of formality x gender fill PER_CELL slots in the order linked, linked, linked, "
    "prospect (cycling): linked = clean contacts with Czech text and a purchase history (every "
    "model level possible: the OCEAN profile is inferred for every linked contact and UC-04 "
    "writes its outputs for the pick); prospect = no purchase history at all; within a kind "
    "ordered by gender_paired DESC, id; stratum = the first STRATUM_SIZE defective rows by id; "
    "briefs = one named brief per category (invitation seasonal_sale_launch, upsell "
    "personal_recommendation, followup review_request_with_reward); briefs per level = the "
    "tiers (0, 1, 2, 3, 5, 6) on every category, each single-field arm on the category where "
    "its field has a place (3a, 3d invitation; 3b, 3c, 4, 6a, 6b, 6d upsell; 6c followup)"
)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _facts(conn: sqlite3.Connection, contact_id: int, tier: str) -> dict[str, Any]:
    """The facts about one picked contact that a results table may split on."""
    c = data.load_contact(conn, contact_id)
    n_orders = conn.execute(
        "SELECT count(*) FROM uc_orders WHERE contact_id = ?", (contact_id,)
    ).fetchone()[0]
    has_uc04 = (
        conn.execute(
            "SELECT 1 FROM uc_recommendations WHERE contact_id = ? LIMIT 1", (contact_id,)
        ).fetchone()
        is not None
    )
    return {
        "id": c.id,
        "name": f"{c.first_name} {c.last_name}",
        "name_vocative": c.name_vocative,
        "gender": c.gender,
        "formal": c.formal,
        "is_clean": c.is_clean,
        "tier": tier,
        "gender_paired": c.gender_paired,
        "reviewer_gender": c.reviewer_gender,
        "ocean_source": c.ocean_source,
        "lifecycle_stage": c.lifecycle_stage,
        "amazon_group": c.amazon_group,
        "orders": n_orders,
        "has_czech": c.style_excerpt is not None,
        "has_uc04": has_uc04,
        "has_role": bool(c.title or c.employer),
    }


def pool_sizes(conn: sqlite3.Connection) -> dict[str, int]:
    """How many contacts each tier holds today."""
    return {
        tier: conn.execute(f"SELECT count(*) FROM uc_contacts c WHERE {sql}").fetchone()[0]
        for tier, sql in TIERS.items()
    }


def core_size(conn: sqlite3.Connection) -> int:
    """How many linked contacts there are today (every model level possible)."""
    return pool_sizes(conn)["linked"]


def pick_reading_set(
    conn: sqlite3.Connection, per_cell: int = PER_CELL
) -> tuple[dict[str, list[int]], dict[int, str]]:
    """Contact ids per (formality, gender) cell by the rule above, and each id's tier."""
    cells: dict[str, list[int]] = {}
    tier_of: dict[int, str] = {}
    for formal in (1, 0):
        for gender in ("m", "f"):
            queues = {
                tier: [
                    r[0]
                    for r in conn.execute(
                        f"SELECT c.id FROM uc_contacts c WHERE {sql} "
                        f"AND c.formal = ? AND c.gender = ? {_ORDER}",
                        (formal, gender),
                    )
                ]
                for tier, sql in TIERS.items()
            }
            chosen: list[int] = []
            for slot in range(per_cell):
                tier = TIER_MIX[slot % len(TIER_MIX)]
                if not queues[tier]:
                    raise LookupError(
                        f"no {tier} contact left for the cell formal={formal} gender={gender}"
                    )
                cid = queues[tier].pop(0)
                chosen.append(cid)
                tier_of[cid] = tier
            cells[f"{'formal' if formal else 'informal'}_{gender}"] = chosen
    return cells, tier_of


def pick_strata(conn: sqlite3.Connection, size: int = STRATUM_SIZE) -> dict[str, list[int]]:
    """The first defective rows by id (the error table)."""
    defective = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM uc_contacts WHERE is_clean = 0 ORDER BY id LIMIT ?", (size,)
        )
    ]
    return {"defective": defective}


def pick_briefs(conn: sqlite3.Connection, briefs: dict[str, str] | None = None) -> list[int]:
    """The id of the named brief of each category, in ``LADDER_BRIEFS`` order."""
    out: list[int] = []
    for category, title in (briefs or LADDER_BRIEFS).items():
        row = conn.execute(
            "SELECT id FROM uc_message_briefs WHERE category = ? AND title = ?",
            (category, title),
        ).fetchone()
        if row is None:
            raise LookupError(
                f"no brief {title!r} in category {category!r}; the corpus is "
                "substrate/snapshots/briefs/message_briefs.json, rebuild the database after editing it"
            )
        out.append(row[0])
    return out


def briefs_by_level(brief_ids: list[int]) -> dict[str, list[int]]:
    """Map every rung to the brief ids it runs on, from LEVEL_BRIEF_CATEGORIES.

    ``brief_ids`` is the output of ``pick_briefs`` (one id per BRIEF_CATEGORIES
    entry, same order). Every ladder id must be mapped; a new rung without a
    row here is a LookupError, not a silent "all briefs".
    """
    if len(brief_ids) != len(BRIEF_CATEGORIES):
        raise LookupError(
            f"expected one brief id per category {BRIEF_CATEGORIES}, got {brief_ids!r}"
        )
    by_category = dict(zip(BRIEF_CATEGORIES, brief_ids, strict=True))
    out: dict[str, list[int]] = {}
    for level_id in levels.LADDER:
        categories = LEVEL_BRIEF_CATEGORIES.get(level_id)
        if categories is None:
            raise LookupError(f"level {level_id!r} has no row in LEVEL_BRIEF_CATEGORIES")
        out[level_id] = [by_category[c] for c in categories]
    return out


def build_pick(
    conn: sqlite3.Connection, *, name: str = DEFAULT_PICK, per_cell: int = PER_CELL
) -> dict[str, Any]:
    """The whole pick as a dict: rule, pool sizes, cells, strata, briefs, per-contact facts."""
    cells, tier_of = pick_reading_set(conn, per_cell)
    strata = pick_strata(conn)
    ids = [i for cell in cells.values() for i in cell]
    briefs = pick_briefs(conn)
    contacts = {str(i): _facts(conn, i, tier_of[i]) for i in ids}
    contacts.update({str(i): _facts(conn, i, "defective") for i in strata["defective"]})
    pools = pool_sizes(conn)
    return {
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": RULE.replace("PER_CELL", str(per_cell)).replace("STRATUM_SIZE", str(STRATUM_SIZE)),
        "tier_mix": [TIER_MIX[i % len(TIER_MIX)] for i in range(per_cell)],
        "pools": pools,
        "core_size": pools["linked"],
        "cells": cells,
        "reading_set": ids,
        "strata": strata,
        "briefs": briefs,
        "briefs_by_level": briefs_by_level(briefs),
        "brief_titles": {
            str(b): conn.execute(
                "SELECT title FROM uc_message_briefs WHERE id = ?", (b,)
            ).fetchone()[0]
            for b in briefs
        },
        "contacts": contacts,
    }


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def pick_path(name: str = DEFAULT_PICK) -> Path:
    """The pick file under ``snapshots/picks/`` for a pick name."""
    return UC01_PICKS_DIR / f"{name}.json"


def write_pick(pick: dict[str, Any], *, overwrite: bool = False) -> Path:
    """Write the pick under ``snapshots/picks/<name>.json``."""
    target = require_can_write(pick_path(pick["name"]), overwrite=overwrite, artifact="pick")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pick, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_pick(name: str = DEFAULT_PICK) -> dict[str, Any]:
    """Read a pick by name; fail with the command that creates it."""
    path = pick_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"pick {name!r} missing: {path}. Create it with `python -m ucs.uc01_personalization pick`."
        )
    return json.loads(path.read_text(encoding="utf-8"))
