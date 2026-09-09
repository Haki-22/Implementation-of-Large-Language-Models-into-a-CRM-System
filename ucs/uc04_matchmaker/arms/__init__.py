"""The arms of the UC-04 arena: one module per recommender, one shared interface.

Every module exposes ``NAME``, ``TITLE``, ``DESCRIPTION``, ``FAMILY``,
``SUPPORTS_POPULATION`` and ``score(arena, *, population=None)`` (see
``_common.py``). ``ARMS`` is the registry the runner, the README and the cards
read; the order here is the order in the tables. The methods that call a language
model have their own registry, ``arms/model/`` (``MODEL_ARMS``), run on the fixed
sample and are never part of ``arena.run``; ``attachment.arms_table`` prints both
registries as the one table of methods the thesis carries.
"""

from __future__ import annotations

from types import ModuleType

from . import (
    adamic_adar,
    als_cf,
    apriori_rules,
    bert_encoder,
    bm25_text,
    dense_e5,
    hybrid_als_dense,
    lightgbm_features,
    naive_bayes,
    popularity,
    svd_mf,
    svm_features,
)

ARMS: dict[str, ModuleType] = {
    m.NAME: m
    for m in (
        popularity,
        als_cf,
        svd_mf,
        apriori_rules,
        adamic_adar,
        naive_bayes,
        bm25_text,
        dense_e5,
        bert_encoder,
        hybrid_als_dense,
        lightgbm_features,
        svm_features,
    )
}

# Arms that need a text encoder and minutes of CPU; ``run --arms fast`` leaves them out.
SLOW = frozenset({dense_e5.NAME, bert_encoder.NAME, hybrid_als_dense.NAME})
POPULATION_CAPABLE = frozenset(name for name, m in ARMS.items() if m.SUPPORTS_POPULATION)


def resolve(spec: str) -> list[str]:
    """Turn ``--arms`` text into arm names: ``all``, ``fast``, ``population`` or a comma list."""
    if spec == "all":
        return list(ARMS)
    if spec == "fast":
        return [n for n in ARMS if n not in SLOW]
    if spec == "population":
        return [n for n in ARMS if n in POPULATION_CAPABLE]
    names = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in ARMS]
    if unknown:
        raise ValueError(f"unknown arm(s) {unknown}; known: {', '.join(ARMS)}")
    return names


__all__ = ["ARMS", "POPULATION_CAPABLE", "SLOW", "resolve"]
