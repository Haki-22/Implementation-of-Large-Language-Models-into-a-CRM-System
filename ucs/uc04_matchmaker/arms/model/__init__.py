"""The model methods of the UC-04 arena: one module per method, one shared interface, one registry.

Every module exposes ``NAME``, ``TITLE``, ``DESCRIPTION``, ``FAMILY``, ``ML_INPUT``
(what a classical model hands the language model, or "none"), ``PROTOCOLS`` (which of
the two protocols the method is scored under), ``SUBSET`` (``sample`` = the fixed
sample of 100, ``reachable`` = the customers whose hidden item ALS placed within its
top 200) and ``async score(inputs, lang) -> MethodOutput`` (``_calls.py``).
``MODEL_ARMS`` is the registry ``model_arena.run``, the README, the cards and the
single methods table of the thesis (``attachment.arms_table``) read; the order here is
the order in the tables. Designed 2026-09-06.
"""

from __future__ import annotations

from types import ModuleType

from . import (
    describe_and_retrieve,
    rank_candidates,
    rerank_als,
    rerank_als_top200,
    rerank_als_with_profile,
)

MODEL_ARMS: dict[str, ModuleType] = {
    m.NAME: m
    for m in (
        rank_candidates,
        describe_and_retrieve,
        rerank_als,
        rerank_als_with_profile,
        rerank_als_top200,
    )
}


def resolve(spec: str) -> list[str]:
    """Turn ``--methods`` text into method names: ``all`` or a comma list."""
    if spec == "all":
        return list(MODEL_ARMS)
    names = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in MODEL_ARMS]
    if unknown:
        raise ValueError(f"unknown method(s) {unknown}; known: {', '.join(MODEL_ARMS)}")
    return names


__all__ = ["MODEL_ARMS", "resolve"]
