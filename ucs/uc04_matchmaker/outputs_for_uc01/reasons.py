"""Recommended products with a Czech sentence saying why, grounded in the purchases the sentence cites.

The products come from ALS collaborative filtering over the whole purchase history (the
same arm as in the arena, nothing hidden), the top ``k`` products the customer has not
bought. The sentence comes from the model, which must cite one to three purchase ids
from the history it was shown; a cited id outside the history, or a sentence longer than
the rule allows, is a failed call, never a silent fix. ``grounded`` records whether every
cited purchase exists.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import numpy as np

from ..arms import als_cf
from ..data import Arena
from ..protocols import mask_history
from . import inputs, prompts
from .calls import Call, Provider, call_json

MAX_WORDS = 30


def recommend(
    arena: Arena, contact_ids: list[int], top_k: int
) -> dict[int, list[tuple[str, float]]]:
    """Contact id -> the top ``k`` unbought products by ALS score (whole history, nothing hidden)."""
    scores = mask_history(als_cf.score(arena), arena)
    by_id = inputs.customers_by_id(arena)
    out: dict[int, list[tuple[str, float]]] = {}
    for cid in contact_ids:
        customer = by_id.get(cid)
        if customer is None:
            continue
        row = scores[arena.customers.index(customer)]
        best = np.argsort(-row)[:top_k]
        out[cid] = [(arena.all_asins[int(j)], float(row[j])) for j in best if np.isfinite(row[j])]
    return out


def validate_reason(parsed: dict[str, Any], id_to_asin: dict[str, str]) -> dict[str, Any]:
    """A schema-valid answer whose evidence ids all exist and whose sentence keeps the word rule."""
    reason = " ".join(str(parsed.get("reason", "")).split())
    if not reason:
        raise ValueError("empty reason")
    if reason.lstrip().startswith("{") or '"reason"' in reason:
        raise ValueError("the reason is JSON, not a sentence")
    if re.search(r"\bH\d{2,3}\b", reason):
        raise ValueError("the reason names purchase ids; they belong in evidence_ids only")
    if len(reason.split()) > MAX_WORDS + 5:  # the schema bounds characters; words are the rule
        raise ValueError(f"reason has {len(reason.split())} words, the rule is {MAX_WORDS}")
    ids = [str(i) for i in parsed.get("evidence_ids") or []]
    unknown = [i for i in ids if i not in id_to_asin]
    if unknown:
        raise ValueError(f"evidence ids not in the history shown: {unknown}")
    return {"reason": reason, "evidence_ids": ids}


async def generate(
    conn,
    arena: Arena,
    contact_ids: list[int],
    *,
    top_k: int,
    provider: Provider,
    run_dir: Path,
    concurrency: int,
) -> dict[int, list[dict[str, Any]]]:
    """Per contact the ``top_k`` recommendations, each with the model's sentence (or the failure)."""
    picks = recommend(arena, contact_ids, top_k)
    labels = inputs.lifecycle_labels(conn, contact_ids)
    by_id = inputs.customers_by_id(arena)
    sem = asyncio.Semaphore(concurrency)
    jobs: list[tuple[int, int, str, float, dict[str, str], Any]] = []
    for cid in contact_ids:
        customer = by_id[cid]
        lines, id_to_asin = inputs.history_lines(customer, arena.catalog)
        for rank, (asin, score) in enumerate(picks.get(cid, []), start=1):
            meta = arena.catalog.get(asin) or {}
            prompt = prompts.reason_prompt(
                cid,
                labels.get(cid, (None, None))[1],
                lines,
                len(customer.history),
                inputs.title_of(arena.catalog, asin),
                (meta.get("categories") or [None])[0],
                meta.get("description"),
            )
            jobs.append((cid, rank, asin, score, id_to_asin, prompt))

    async def one(
        cid: int, rank: int, asin: str, score: float, id_to_asin: dict[str, str], prompt: str
    ) -> tuple[int, dict[str, Any]]:
        """Call the model for one recommendation's reason and assemble its result row."""
        call: Call = await call_json(
            kind="reasons",
            key=f"{cid}-{rank}",
            prompt=prompt,
            system_prompt=prompts.REASON_SYSTEM,
            schema=prompts.REASON_SCHEMA,
            provider=provider,
            run_dir=run_dir,
            sem=sem,
            validate=lambda parsed, m=id_to_asin: validate_reason(parsed, m),
        )
        row = {
            "rank": rank,
            "asin": asin,
            "title": inputs.title_of(arena.catalog, asin),
            "score": round(score, 4),
            "source": "als_cf (whole history)",
            "status": call.status,
            "seconds": call.seconds,
            "reason": call.parsed["reason"] if call.parsed else None,
            "evidence_ids": call.parsed["evidence_ids"] if call.parsed else [],
            "evidence_asin": [
                id_to_asin[i] for i in (call.parsed["evidence_ids"] if call.parsed else [])
            ],
            "grounded": bool(call.parsed),
            "error": call.error,
        }
        return cid, row

    results = await asyncio.gather(*(one(*job) for job in jobs))
    out: dict[int, list[dict[str, Any]]] = {cid: [] for cid in contact_ids}
    for cid, row in results:
        out[cid].append(row)
    for rows in out.values():
        rows.sort(key=lambda r: r["rank"])
    return out


__all__ = ["MAX_WORDS", "generate", "recommend", "validate_reason"]
