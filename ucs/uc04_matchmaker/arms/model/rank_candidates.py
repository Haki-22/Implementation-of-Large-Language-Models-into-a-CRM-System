"""Method 1: the model orders the candidates itself, with no classical input.

The customer's whole purchase history and the sampled candidate list (1 hidden + 100
never-bought products, the same list every classical arm was scored on) go into one
prompt; the candidates are in a seeded random order per customer so the hidden item
does not stand at a fixed position (design §8.4). The model returns the full
permutation. What it measures: a language model without any training on the shop
against the classical arms on identical lists, and the Czech tax when the titles and
the instruction are Czech.
"""

from __future__ import annotations

from ...protocols import sample_candidates
from . import _prompts
from ._calls import Inputs, MethodOutput, run_ranking, shuffled, subset_arena

NAME = "rank_candidates"
TITLE = "Model ranks the candidates alone"
DESCRIPTION = (
    "whole history + the 101 sampled candidates in a seeded random order; the model returns "
    "the full permutation; no classical input"
)
FAMILY = "language model / zero-shot ranking"
ML_INPUT = "none"
PROTOCOLS = ("sampled",)
SUBSET = "sample"


async def score(inputs: Inputs, lang: str) -> MethodOutput:
    """Rank the 101 sampled candidates per customer with one model call each, no classical input shown."""
    arena = subset_arena(inputs.arenas[lang], inputs.target_ids)
    candidates = sample_candidates(arena, n_neg=inputs.n_neg, seed=inputs.seed)
    lists = [
        (shuffled(cand, seed=inputs.seed, contact_id=c.contact_id), None)
        for c, cand in zip(arena.customers, candidates, strict=True)
    ]
    records, scores = await run_ranking(
        inputs,
        method=NAME,
        arena=arena,
        system_prompt=_prompts.system_text("ranking", lang),
        lists=lists,
        als_order_shown=False,
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
