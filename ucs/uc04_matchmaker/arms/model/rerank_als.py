"""Method 3: the model re-orders the candidates from ALS.

The same 101 sampled candidates as method 1, but listed in the order ALS collaborative
filtering ranked them, each with its ALS score; the instruction says to keep that order
unless the history supports a move. What it measures: whether the model improves,
worsens or leaves the classical order on identical lists, the complement-versus-
replacement question of the use case, paired per customer against ALS.
"""

from __future__ import annotations

from ...protocols import sample_candidates
from . import _prompts
from ._calls import Inputs, MethodOutput, als_order, run_ranking, subset_arena

NAME = "rerank_als"
TITLE = "Model re-ranks the ALS order"
DESCRIPTION = (
    "whole history + the 101 sampled candidates in ALS order with their scores; the model "
    "may move a candidate only where the history supports it"
)
FAMILY = "language model / re-ranking over collaborative filtering"
ML_INPUT = "ALS order and scores of the 101 sampled candidates"
PROTOCOLS = ("sampled",)
SUBSET = "sample"


async def score(inputs: Inputs, lang: str) -> MethodOutput:
    """Re-rank the 101 sampled candidates per customer, shown in ALS order with scores."""
    arena = subset_arena(inputs.arenas[lang], inputs.target_ids)
    candidates = sample_candidates(arena, n_neg=inputs.n_neg, seed=inputs.seed)
    lists = [
        als_order(inputs, c, cand) for c, cand in zip(arena.customers, candidates, strict=True)
    ]
    records, scores = await run_ranking(
        inputs,
        method=NAME,
        arena=arena,
        system_prompt=_prompts.system_text("ranking", lang, als_order=True),
        lists=lists,
        als_order_shown=True,
    )
    return MethodOutput(arena=arena, scores=scores, calls=records, candidates=candidates)


__all__ = [
    "DESCRIPTION",
    "FAMILY",
    "ML_INPUT",
    "NAME",
    "PROTOCOLS",
    "SUBSET",
    "TITLE",
    "score",
]
