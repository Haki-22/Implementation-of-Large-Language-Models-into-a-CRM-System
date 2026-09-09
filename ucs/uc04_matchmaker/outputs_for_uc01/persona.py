"""The persona: two Czech sentences about how the customer buys, from behaviour only.

Input: the most bought categories, the number of purchases and the mean rating, the
lifecycle stage, the interest topics (classical) and the longest Czech reviews, cut
short. Output: a slug label, the two sentences, three to five tags and a price segment.
The persona is not loaded into the database today (UC-01 has no slot for it); it goes
into the handoff file and the appendix as the category C artefact the assignment names.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from pathlib import Path
from typing import Any

from ..data import Arena
from . import inputs, prompts
from .calls import Provider, call_json


def slug(label: str) -> str:
    """Lower-case ASCII letters, digits and underscores (a persona label is a tag, not prose)."""
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_") or "persona"


async def generate(
    conn,
    arena: Arena,
    contact_ids: list[int],
    topics: dict[int, list[dict[str, Any]]],
    *,
    provider: Provider,
    run_dir: Path,
    concurrency: int,
) -> dict[int, dict[str, Any]]:
    """Per contact the persona (or the failure)."""
    labels = inputs.lifecycle_labels(conn, contact_ids)
    by_id = inputs.customers_by_id(arena)
    sem = asyncio.Semaphore(concurrency)

    async def one(cid: int) -> tuple[int, dict[str, Any]]:
        """Call the model for one contact's persona and slug its label."""
        customer = by_id[cid]
        reviews = inputs.czech_reviews(conn, cid)
        prompt = prompts.persona_prompt(
            cid,
            len(customer.history),
            inputs.mean_rating(customer),
            labels.get(cid, (None, None))[1],
            inputs.top_categories(customer, arena.catalog),
            [t["label"] for t in topics.get(cid, [])[:3]],
            inputs.review_samples(reviews),
        )
        call = await call_json(
            kind="persona",
            key=str(cid),
            prompt=prompt,
            system_prompt=prompts.PERSONA_SYSTEM,
            schema=prompts.PERSONA_SCHEMA,
            provider=provider,
            run_dir=run_dir,
            sem=sem,
        )
        parsed = dict(call.parsed or {})
        if parsed.get("label"):
            parsed["label"] = slug(parsed["label"])
        return cid, {
            "status": call.status,
            "seconds": call.seconds,
            "error": call.error,
            **parsed,
        }

    return dict(await asyncio.gather(*(one(cid) for cid in contact_ids)))


__all__ = ["generate", "slug"]
