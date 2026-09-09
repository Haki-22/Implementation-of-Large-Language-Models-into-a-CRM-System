"""The fixed customer sample the model arms and the OCEAN inference run on, chosen by a rule and written down.

A language-model arm costs one call per customer and branch, so it cannot run on
all 425 linked customers the way a classical arm does. It runs on a fixed,
stratified sample instead (decision of 2026-09-06, map section 10d): 100
customers, 60 of group A, 20 of B, 20 of C, the same list for every model arm and
for the OCEAN inference that feeds the profile re-ranker. The rule: within each
group, the linked contacts of UC-01's pick first, in contact-id order, so that the
recommendations the model explains and the personality it infers belong to the
people whose messages UC-01's reading pass looks at; then a seeded random draw
without replacement from the arena's remaining customers of that group. The
sample is a committed file under ``eval/samples/``: the rule in words, the seed,
the ids per group and per customer the facts a table may split on. Every run that
uses it copies it into its own folder.

Run:
    python -m ucs.uc04_matchmaker sample                 # writes eval/samples/model-arms-100.json
    python -m ucs.uc04_matchmaker sample --force         # regenerate (same rule, same seed = same ids)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from utils.file_safety import require_can_write
from utils.paths import UC04_SAMPLES_DIR

from .data import Customer, load_customers

DEFAULT_SAMPLE = "model-arms-100"
# The committed sample was drawn on 2026-09-06 from UC-01's pick of that day,
# `reading-16` (its 16 members are marked ``pick_tier`` in the file). The pick was
# redrawn on 2026-09-07 (D-UC01-6) and the sample deliberately was not (pending 14:
# the model methods had run on it; who is in UC-01's pick does not change what
# the sample measures). Do not run ``sample --force`` unless the model methods
# are rerun on the new file.
DEFAULT_PICK = "uc01-personalization-20-level"
QUOTAS: dict[str, int] = {"A": 60, "B": 20, "C": 20}
SEED = 42

RULE = (
    "the arena's linked customers (at least two reviews) split by group; per group fill QUOTAS "
    "slots: first the linked contacts of UC-01's pick PICK that belong to the group, in contact-id "
    "order, then a random draw without replacement from the group's remaining customers with "
    "numpy default_rng([SEED, group index]); ids sorted; one list for every model arm and for the "
    "OCEAN inference"
)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def pick_members(pick: dict[str, Any] | None) -> dict[int, str]:
    """Contact id -> tier for the pick's contacts that own a reviewer; prospects have no history."""
    if not pick:
        return {}
    return {
        int(cid): facts["tier"]
        for cid, facts in pick.get("contacts", {}).items()
        if facts.get("amazon_group")
    }


def _ocean_sources(conn: sqlite3.Connection, ids: list[int]) -> dict[int, str | None]:
    """``ocean_source`` per contact at the time the sample is written (a toy table may lack the column)."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(uc_contacts)")}
    if "ocean_source" not in columns or not ids:
        return {i: None for i in ids}
    marks = ",".join("?" * len(ids))
    return {
        row[0]: row[1]
        for row in conn.execute(
            f"SELECT id, ocean_source FROM uc_contacts WHERE id IN ({marks})", ids
        )
    }


def build_sample(
    conn: sqlite3.Connection,
    *,
    pick: dict[str, Any] | None,
    pick_name: str | None,
    name: str = DEFAULT_SAMPLE,
    quotas: dict[str, int] | None = None,
    seed: int = SEED,
) -> dict[str, Any]:
    """The whole sample as a dict: rule, seed, quotas, ids per group, per-customer facts.

    Raises:
        LookupError: a group has fewer customers than its quota, or more pick members than slots.
    """
    quotas = dict(quotas or QUOTAS)
    customers = load_customers(conn, "en")
    by_group: dict[str, list[Customer]] = {}
    for c in customers:
        by_group.setdefault(c.group, []).append(c)
    forced = pick_members(pick)

    groups: dict[str, list[Customer]] = {}
    forced_counts: dict[str, int] = {}
    for index, (group, quota) in enumerate(sorted(quotas.items())):
        members = sorted(by_group.get(group, []), key=lambda c: c.contact_id)
        first = [c for c in members if c.contact_id in forced]
        if len(first) > quota:
            raise LookupError(
                f"group {group}: {len(first)} pick members but only {quota} slots; raise the quota"
            )
        rest = [c for c in members if c.contact_id not in forced]
        need = quota - len(first)
        if need > len(rest):
            raise LookupError(
                f"group {group}: quota {quota} but only {len(members)} customers in the arena"
            )
        rng = np.random.default_rng([seed, index])
        drawn = [rest[i] for i in rng.choice(len(rest), size=need, replace=False)] if need else []
        groups[group] = sorted(first + drawn, key=lambda c: c.contact_id)
        forced_counts[group] = len(first)

    ordered = sorted((c for chosen in groups.values() for c in chosen), key=lambda c: c.contact_id)
    ocean_source = _ocean_sources(conn, [c.contact_id for c in ordered])
    rule = RULE.replace("QUOTAS", json.dumps(quotas)).replace("SEED", str(seed))
    rule = rule.replace("PICK", pick_name or "(none)")
    return {
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": rule,
        "seed": seed,
        "quotas": quotas,
        "pick": {"name": pick_name, "members_per_group": forced_counts},
        "arena": {
            "linked_customers": len(customers),
            "per_group": {g: len(v) for g, v in sorted(by_group.items())},
        },
        "groups": {g: [c.contact_id for c in chosen] for g, chosen in groups.items()},
        "contact_ids": [c.contact_id for c in ordered],
        "reviewer_ids": [c.reviewer_id for c in ordered],
        "contacts": {
            str(c.contact_id): {
                "id": c.contact_id,
                "reviewer_id": c.reviewer_id,
                "group": c.group,
                "pick_tier": forced.get(c.contact_id),
                "reviews": len(c.history) + 1,
                "ocean_source": ocean_source.get(c.contact_id),
            }
            for c in ordered
        },
    }


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def sample_path(name: str = DEFAULT_SAMPLE, base: Path = UC04_SAMPLES_DIR) -> Path:
    """The sample file under ``eval/samples/`` for a sample name."""
    return base / f"{name}.json"


def write_sample(
    sample: dict[str, Any], *, overwrite: bool = False, base: Path = UC04_SAMPLES_DIR
) -> Path:
    """Write the sample under ``eval/samples/<name>.json``."""
    target = require_can_write(
        sample_path(sample["name"], base), overwrite=overwrite, artifact="sample"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_sample(name: str = DEFAULT_SAMPLE, base: Path = UC04_SAMPLES_DIR) -> dict[str, Any]:
    """Read a sample by name; fail with the command that creates it."""
    path = sample_path(name, base)
    if not path.exists():
        raise FileNotFoundError(
            f"sample {name!r} missing: {path}. Create it with `python -m ucs.uc04_matchmaker sample`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "DEFAULT_PICK",
    "DEFAULT_SAMPLE",
    "QUOTAS",
    "RULE",
    "SEED",
    "build_sample",
    "load_sample",
    "pick_members",
    "sample_path",
    "write_sample",
]
