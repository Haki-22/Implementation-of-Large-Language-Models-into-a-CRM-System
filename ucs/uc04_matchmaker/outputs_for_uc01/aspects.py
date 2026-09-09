"""The product aspects the customer praises or criticises, each with a verbatim quote from their Czech reviews.

The model reads the customer's Czech reviews (newest first, capped) and names three to
five aspects with a sentiment and a quote. The quote must be in the review text: the
check normalises whitespace and case and looks for the quote as a substring; a quote
that is not there marks the aspect ``grounded: false`` (the row stays, the card counts
it), because a paraphrase is exactly what the rule forbids.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from . import inputs, prompts
from .calls import Provider, call_json


_QUOTES = re.compile(r"[\"'„“”‚‘’«»]")


def _normalise(text: str) -> str:
    """Whitespace collapsed, case folded, quotation marks dropped (a translator's „“ against the model's "" is not a paraphrase)."""
    return re.sub(r"\s+", " ", _QUOTES.sub("", text)).strip().casefold()


def quote_found(quote: str, review_text: str) -> bool:
    """Whether ``quote`` occurs verbatim (whitespace, case and quotation marks aside) in ``review_text``."""
    q = _normalise(quote).strip(" .,;:!?")
    return bool(q) and q in _normalise(review_text)


async def generate(
    conn,
    contact_ids: list[int],
    *,
    provider: Provider,
    run_dir: Path,
    concurrency: int,
) -> dict[int, dict[str, Any]]:
    """Per contact the aspects with their grounding (or the failure, or ``skipped`` without Czech reviews)."""
    sem = asyncio.Semaphore(concurrency)

    async def one(cid: int) -> tuple[int, dict[str, Any]]:
        """Call the model for one contact's aspects and score each returned quote for grounding."""
        reviews = inputs.czech_reviews(conn, cid)
        if not reviews:
            return cid, {
                "status": "skipped",
                "seconds": 0.0,
                "error": "no Czech reviews",
                "aspects": [],
            }
        block, shown = inputs.review_block(reviews)
        prompt = prompts.aspects_prompt(cid, len(reviews), block, shown)
        call = await call_json(
            kind="aspects",
            key=str(cid),
            prompt=prompt,
            system_prompt=prompts.ASPECTS_SYSTEM,
            schema=prompts.ASPECTS_SCHEMA,
            provider=provider,
            run_dir=run_dir,
            sem=sem,
        )
        rows = []
        for item in (call.parsed or {}).get("aspects") or []:
            rows.append(
                {
                    "aspect": str(item.get("aspect", "")).strip(),
                    "sentiment": str(item.get("sentiment", "")),
                    "evidence": str(item.get("evidence", "")).strip(),
                    "grounded": quote_found(str(item.get("evidence", "")), block),
                }
            )
        return cid, {
            "status": call.status,
            "seconds": call.seconds,
            "error": call.error,
            "reviews": len(reviews),
            "chars_shown": shown,
            "aspects": rows,
        }

    return dict(await asyncio.gather(*(one(cid) for cid in contact_ids)))


__all__ = ["generate", "quote_found"]
