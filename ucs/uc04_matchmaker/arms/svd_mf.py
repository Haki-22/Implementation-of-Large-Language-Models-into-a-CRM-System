"""SVD matrix factorisation: the Netflix-Prize-era factorisation of the rating matrix (formerly arm b11).

Truncated SVD of the explicit customer x product rating matrix, 50 factors; the
predicted rating is the dot product of the customer and product factors. Same
paradigm as ALS with a different solver and explicit ratings; it is kept as the
check that the collaborative-filtering result does not hang on one library.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse.linalg import svds

from ..data import Arena
from ..population import Population, project_scores
from ._common import interaction_matrix

NAME = "svd_mf"
TITLE = "SVD matrix factorisation"
DESCRIPTION = "truncated SVD of the explicit rating matrix, 50 factors"
FAMILY = "classical / collaborative filtering"
SUPPORTS_POPULATION = True

FACTORS = 50


def _fit(matrix):
    """Truncated SVD of `matrix` to `FACTORS` factors; return `(user_factors, item_factors)`."""
    u, s, vt = svds(matrix.astype(np.float32), k=FACTORS, random_state=42)
    return (u * s).astype(np.float32), vt.T.astype(np.float32)


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Reconstructed ratings over the shop catalogue."""
    if population is None:
        user_f, item_f = _fit(interaction_matrix(arena, confidence=False))
        return user_f @ item_f.T
    user_f, item_f = _fit(population.matrix)
    return project_scores(arena, population, user_f, item_f)


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
