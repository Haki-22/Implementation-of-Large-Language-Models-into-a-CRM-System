"""Method 2: the model describes the next purchase in words, the dense catalogue index finds it.

The model reads the whole history and writes three listing-style lines for the most
likely next purchase (type, brand, the attribute that matters), in the language of
the titles. Each line is encoded with the same ``multilingual-e5-base`` and the same
cached catalogue vectors as the ``dense_e5`` arm (``query:`` prefix for the lines,
``passage:`` for the products); a product's score is the largest cosine similarity
over the three lines, so the method returns a score for the whole catalogue and is
evaluated under both protocols like a classical arm. The only "model alone" method
that can reach the whole catalogue; the lines themselves are the category-C output
no classical arm has, and the appendix shows a few beside the real hidden purchase.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from ...data import Arena
from ...protocols import NEG_INF, sample_candidates
from .. import dense_e5
from . import _prompts
from ._calls import Inputs, MethodOutput, history_lines, recorded_call, subset_arena

NAME = "describe_and_retrieve"
TITLE = "Model describes the next purchase, the catalogue index retrieves it"
DESCRIPTION = (
    "whole history -> three listing lines for the next purchase -> multilingual-e5 query "
    "vectors against the cached catalogue vectors; score = best cosine over the three lines"
)
FAMILY = "language model / description + dense retrieval"
ML_INPUT = "the dense e5 index of the catalogue (the dense_e5 arm's cached vectors)"
PROTOCOLS = ("full", "sampled")
SUBSET = "sample"

_encoder = None


def item_vectors(arena: Arena) -> np.ndarray:
    """The catalogue vectors of the branch (the ``dense_e5`` cache)."""
    return dense_e5.item_embeddings(arena)


def query_vectors(texts: list[str]) -> np.ndarray:
    """Normalised e5 vectors of the model's lines, ``query:`` prefixed as the encoder expects."""
    global _encoder
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    if _encoder is None:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(dense_e5.MODEL)
    return _encoder.encode(
        [f"query: {t}" for t in texts],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).astype(np.float32)


def _interpret(raw: Any) -> tuple[dict[str, Any], str, str]:
    """Keep up to 3 non-empty `next_purchases` lines from `raw`; `ok` with 3, `partial` with fewer, `failed` with none."""
    lines = raw.get("next_purchases") if isinstance(raw, dict) else None
    if not isinstance(lines, list):
        return {}, "failed", "answer has no 'next_purchases' list"
    clean = [" ".join(str(x).split()) for x in lines if str(x).strip()]
    if not clean:
        return {}, "failed", "no usable line"
    status = "ok" if len(clean) >= 3 else "partial"
    return {"next_purchases": clean[:3]}, status, "" if status == "ok" else f"{len(clean)} lines"


async def score(inputs: Inputs, lang: str) -> MethodOutput:
    """Have the model describe each customer's next purchase, then retrieve the catalogue by cosine similarity to those lines."""
    arena = subset_arena(inputs.arenas[lang], inputs.target_ids)
    sem = asyncio.Semaphore(inputs.concurrency)
    tasks = [
        recorded_call(
            inputs,
            method=NAME,
            lang=lang,
            contact_id=c.contact_id,
            prompt=_prompts.user_prompt(
                lang,
                contact_id=c.contact_id,
                history_lines=history_lines(c, arena),
                candidate_lines=None,
            ),
            system_prompt=_prompts.system_text("describe", lang),
            schema=_prompts.DESCRIBE_SCHEMA,
            sem=sem,
            interpret=_interpret,
            extra={"held_out": c.held_out.asin},
        )
        for c in arena.customers
    ]
    records = list(await asyncio.gather(*tasks))
    sentences: dict[int, list[str]] = {
        r.contact_id: list((r.parsed or {}).get("next_purchases") or []) for r in records
    }
    flat = [(u, s) for u, r in enumerate(records) for s in sentences[r.contact_id]]
    items = item_vectors(arena)
    scores = np.full((arena.n_customers, arena.n_items), NEG_INF, dtype=np.float32)
    if flat:
        q = query_vectors([s for _, s in flat])
        sims = q @ items.T
        for n, (u, _) in enumerate(flat):
            scores[u] = np.where(scores[u] > sims[n], scores[u], sims[n])
    candidates = sample_candidates(arena, n_neg=inputs.n_neg, seed=inputs.seed)
    return MethodOutput(
        arena=arena,
        scores=scores,
        calls=records,
        candidates=candidates,
        extras={"sentences": {str(cid): s for cid, s in sentences.items()}},
    )


__all__ = [
    "DESCRIPTION",
    "FAMILY",
    "ML_INPUT",
    "NAME",
    "PROTOCOLS",
    "SUBSET",
    "TITLE",
    "item_vectors",
    "query_vectors",
    "score",
]
