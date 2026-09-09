"""Popularity: recommend what most customers bought. The reference row every other arm must beat."""

from __future__ import annotations

import numpy as np

from ..data import Arena
from ..population import Population
from ._common import empty_scores, interaction_matrix

NAME = "popularity"
TITLE = "Most-bought products"
DESCRIPTION = "ranks every product by how many customers bought it; no personalisation"
FAMILY = "classical / baseline"
SUPPORTS_POPULATION = True


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Buyer count per product, identical for every customer."""
    if population is None:
        counts = np.asarray((interaction_matrix(arena) > 0).sum(axis=0)).ravel().astype(np.float32)
        return np.tile(counts, (arena.n_customers, 1))
    counts_all = np.asarray((population.matrix > 0).sum(axis=0)).ravel().astype(np.float32)
    cols, positions = population.shop_columns(arena)
    scores = empty_scores(arena)
    scores[:, positions] = counts_all[cols]
    return scores


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
