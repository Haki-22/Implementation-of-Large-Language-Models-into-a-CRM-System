"""Method 5: the model re-orders the 200 best ALS candidates under the full catalogue.

The only honest test against the whole catalogue: for the customers whose hidden last
purchase sits inside ALS's top 200 (45 of 425 in the run of record; measured again at
run time from the same seeded ALS), the model receives those 200 in ALS order with the
scores and may pull the right product up into the top 10. Everyone else is not called,
because a re-ranker cannot hit what its retriever did not hand it (map §10c). Scored
under the full protocol, paired against ALS on the same customers.
"""

from __future__ import annotations

from ...data import Arena
from . import _prompts
from ._calls import Inputs, MethodOutput, als_top, run_ranking, subset_arena

NAME = "rerank_als_top200"
TITLE = "Model re-ranks the ALS top 200 (full catalogue)"
DESCRIPTION = (
    "for the customers whose hidden item ALS placed within its top 200: those 200 in ALS "
    "order with scores, the model re-orders them; the honest test against the whole catalogue"
)
FAMILY = "language model / re-ranking over collaborative filtering"
ML_INPUT = "ALS top 200 of the whole catalogue, with scores"
PROTOCOLS = ("full",)
SUBSET = "reachable"
TOP_K = 200


def reachable(inputs: Inputs, k: int = TOP_K) -> dict[int, tuple[list[int], list[float], int]]:
    """Contact id -> (ALS top-``k`` items, their scores, the hidden item's 1-based position) where the hidden item is inside."""
    arena: Arena = inputs.arenas["en"]
    out: dict[int, tuple[list[int], list[float], int]] = {}
    for c in arena.customers:
        top, scores = als_top(inputs, c, k)
        target = arena.asin_to_idx.get(c.held_out.asin)
        if target is not None and target in top:
            out[c.contact_id] = (top, scores, top.index(target) + 1)
    return out


async def score(inputs: Inputs, lang: str) -> MethodOutput:
    """Re-rank ALS's top-200 candidates for the customers whose hidden item falls inside it; everyone else is skipped."""
    within = reachable(inputs)
    ids = sorted(within)
    if inputs.limit is not None:
        ids = ids[: inputs.limit]
    arena = subset_arena(inputs.arenas[lang], ids)
    lists = [(within[c.contact_id][0], within[c.contact_id][1]) for c in arena.customers]
    records, scores = await run_ranking(
        inputs,
        method=NAME,
        arena=arena,
        system_prompt=_prompts.system_text("ranking", lang, als_order=True),
        lists=lists,
        als_order_shown=True,
    )
    return MethodOutput(
        arena=arena,
        scores=scores,
        calls=records,
        extras={
            "reachable": ids,
            "top_k": TOP_K,
            "hidden_position_in_als": {str(cid): within[cid][2] for cid in ids},
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
    "TOP_K",
    "reachable",
    "score",
]
