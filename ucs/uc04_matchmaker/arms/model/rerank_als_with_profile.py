"""Method 4: method 3 plus the customer profile the CRM holds.

The same prompt as ``rerank_als`` (the 101 sampled candidates in ALS order) with a
profile block: the Big Five estimate the database carries (inferred from the reviews
for every linked customer since 2026-09-06, or the generator's sampled one), the
lifecycle stage, the interest topics (LDA over the Czech titles, ``uc_topics``) and,
where the outputs for UC-01 produced them, the persona and the praised or criticised
aspects (``uc_aspects``; the persona lives only in the handoff file). The instruction
says the profile breaks ties only. Which fields each customer had is written into the
run's ``config.json``; the persona and the aspects are Czech in both branches, which
the card states. What it measures, paired against method 3 on the same customers:
whether the inputs of hyper-personalisation change the recommendation for the better.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from utils.paths import SUBSTRATE_DB, UC04_HANDOFF

from ...data import connect
from ...protocols import sample_candidates
from . import _prompts
from ._calls import Inputs, MethodOutput, als_order, run_ranking, subset_arena

NAME = "rerank_als_with_profile"
TITLE = "Model re-ranks the ALS order with the customer profile"
DESCRIPTION = (
    "method 3 plus the profile from the CRM: Big Five estimate, lifecycle stage, interest "
    "topics, persona and aspects where present; the profile breaks ties only"
)
FAMILY = "language model / re-ranking over collaborative filtering + profile"
ML_INPUT = "ALS order and scores of the 101 sampled candidates; the profile from the database"
PROTOCOLS = ("sampled",)
SUBSET = "sample"

TRAITS = ("O", "C", "E", "A", "N")
TOPICS_PER_CUSTOMER = 3
_SENTIMENT_WORDS = {
    "en": {"positive": "praised", "negative": "criticised", "mixed": "mixed"},
    "cs": {"positive": "chválí", "negative": "kritizuje", "mixed": "smíšeně"},
}


# ---------------------------------------------------------------------------
# Reading the profile
# ---------------------------------------------------------------------------


def _tables(conn: sqlite3.Connection) -> set[str]:
    """Names of every table in the SQLite database `conn` is connected to."""
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Column names of `table`."""
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def load_profiles(
    contact_ids: list[int],
    *,
    lang: str,
    db_path: Path = SUBSTRATE_DB,
    handoff_path: Path = UC04_HANDOFF,
) -> dict[int, dict[str, Any]]:
    """Contact id -> the profile fields the database (and the handoff) hold for it.

    Every field is optional; a toy database without the columns yields empty profiles.
    """
    profiles: dict[int, dict[str, Any]] = {cid: {} for cid in contact_ids}
    if not contact_ids:
        return profiles
    marks = ",".join("?" * len(contact_ids))
    conn = connect(db_path)
    try:
        tables = _tables(conn)
        contact_cols = _columns(conn, "uc_contacts")
        label_col = "label_cs" if lang == "cs" else "label_en"
        has_stages = "uc_lifecycle_stages" in tables and label_col in _columns(
            conn, "uc_lifecycle_stages"
        )
        select = ["c.id", "c.reviewer_id"]
        select.append("c.ocean" if "ocean" in contact_cols else "NULL AS ocean")
        select.append(
            "c.ocean_source" if "ocean_source" in contact_cols else "NULL AS ocean_source"
        )
        if has_stages and "lifecycle_stage" in contact_cols:
            select.append(f"s.{label_col} AS lifecycle")
            join = "LEFT JOIN uc_lifecycle_stages s ON s.code = c.lifecycle_stage"
        else:
            select.append("NULL AS lifecycle")
            join = ""
        reviewer_of: dict[int, str | None] = {}
        for row in conn.execute(
            f"SELECT {', '.join(select)} FROM uc_contacts c {join} WHERE c.id IN ({marks})",
            contact_ids,
        ):
            cid = int(row["id"])
            reviewer_of[cid] = row["reviewer_id"]
            ocean = row["ocean"]
            if isinstance(ocean, str):
                try:
                    ocean = json.loads(ocean)
                except json.JSONDecodeError:
                    ocean = None
            if isinstance(ocean, dict) and all(t in ocean for t in TRAITS):
                profiles[cid]["ocean"] = {t: float(ocean[t]) for t in TRAITS}
                profiles[cid]["ocean_source"] = row["ocean_source"]
            if row["lifecycle"]:
                profiles[cid]["lifecycle"] = row["lifecycle"]
        if "uc_topics" in tables:
            for row in conn.execute(
                f"SELECT contact_id, label FROM uc_topics WHERE contact_id IN ({marks}) "
                "ORDER BY contact_id, rank",
                contact_ids,
            ):
                topics = profiles[int(row["contact_id"])].setdefault("topics", [])
                if len(topics) < TOPICS_PER_CUSTOMER:
                    topics.append(row["label"])
        if "uc_aspects" in tables:
            for row in conn.execute(
                f"SELECT contact_id, aspect, sentiment FROM uc_aspects WHERE contact_id IN ({marks}) "
                "ORDER BY contact_id, id",
                contact_ids,
            ):
                profiles[int(row["contact_id"])].setdefault("aspects", []).append(
                    (row["aspect"], row["sentiment"])
                )
    finally:
        conn.close()
    if Path(handoff_path).exists():
        users = json.loads(Path(handoff_path).read_text(encoding="utf-8")).get("users", {})
        for cid, reviewer in reviewer_of.items():
            persona = (users.get(reviewer) or {}).get("persona") or {}
            if persona.get("narrative_cs"):
                profiles[cid]["persona"] = persona["narrative_cs"]
    return profiles


def _number(x: float, lang: str) -> str:
    """`x` formatted to one decimal, with a comma decimal separator in the Czech branch."""
    s = f"{x:.1f}"
    return s.replace(".", ",") if lang == "cs" else s


def profile_lines(profile: dict[str, Any], lang: str) -> list[str]:
    """The profile block of the prompt: only the fields the customer has."""
    w = _prompts.words(lang)
    sep = "; " if lang == "cs" else ", "
    out: list[str] = []
    if profile.get("ocean"):
        traits = sep.join(f"{t} {_number(profile['ocean'][t], lang)}" for t in TRAITS)
        out.append(f"- {w['big_five']}: {traits}")
    if profile.get("lifecycle"):
        out.append(f"- {w['lifecycle']}: {profile['lifecycle']}")
    if profile.get("topics"):
        out.append(f"- {w['topics']}: {'; '.join(profile['topics'])}")
    if profile.get("persona"):
        out.append(f"- {w['persona']}: {profile['persona']}")
    if profile.get("aspects"):
        groups: dict[str, list[str]] = {}
        for aspect, sentiment in profile["aspects"]:
            groups.setdefault(sentiment, []).append(aspect)
        names = _SENTIMENT_WORDS[lang]
        parts = [f"{names.get(s, s)}: {', '.join(a)}" for s, a in groups.items()]
        out.append(f"- {w['aspects']}: {'; '.join(parts)}")
    return out


# ---------------------------------------------------------------------------
# The method
# ---------------------------------------------------------------------------


async def score(inputs: Inputs, lang: str) -> MethodOutput:
    """Re-rank the ALS-ordered sampled candidates with the customer's CRM profile appended as a tie-breaker."""
    arena = subset_arena(inputs.arenas[lang], inputs.target_ids)
    candidates = sample_candidates(arena, n_neg=inputs.n_neg, seed=inputs.seed)
    lists = [
        als_order(inputs, c, cand) for c, cand in zip(arena.customers, candidates, strict=True)
    ]
    profiles = load_profiles(
        [c.contact_id for c in arena.customers], lang=lang, db_path=inputs.db_path or SUBSTRATE_DB
    )
    lines = {cid: profile_lines(p, lang) for cid, p in profiles.items()}
    records, scores = await run_ranking(
        inputs,
        method=NAME,
        arena=arena,
        system_prompt=_prompts.system_text("ranking", lang, als_order=True, profile=True),
        lists=lists,
        als_order_shown=True,
        profile_lines=lines,
    )
    return MethodOutput(
        arena=arena,
        scores=scores,
        calls=records,
        candidates=candidates,
        extras={
            "profile_fields": {
                str(cid): sorted(k for k in p if k != "ocean_source") for cid, p in profiles.items()
            },
            "ocean_sources": {
                str(cid): p.get("ocean_source") for cid, p in profiles.items() if p.get("ocean")
            },
        },
    )


__all__ = [
    "DESCRIPTION",
    "FAMILY",
    "ML_INPUT",
    "NAME",
    "PROTOCOLS",
    "SUBSET",
    "TITLE",
    "load_profiles",
    "profile_lines",
    "score",
]
