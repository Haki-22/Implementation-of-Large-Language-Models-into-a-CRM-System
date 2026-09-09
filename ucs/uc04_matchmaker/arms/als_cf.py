"""ALS collaborative filtering: latent tastes from who bought what (formerly arm b1).

Implicit-feedback alternating least squares (Hu, Koren & Volinsky 2008) over the
customer x product matrix, a purchase weighted by ``1 + rating`` as confidence.
Language-agnostic: it never reads text, so the English and Czech branches must
agree exactly; a difference would be a data defect, not a language effect. In the
population regime the same model learns from every reviewer in the public dump
and is applied to the shop's customers.
"""

from __future__ import annotations

import numpy as np

from ..data import Arena
from ..population import Population, project_scores
from ._common import interaction_matrix

NAME = "als_cf"
TITLE = "ALS collaborative filtering"
DESCRIPTION = (
    "latent factors from who bought what; a purchase weighs 1 + rating; 64 factors, 20 iterations"
)
FAMILY = "classical / collaborative filtering"
SUPPORTS_POPULATION = True

FACTORS = 64
ITERATIONS = 20
REGULARIZATION = 0.01
SEED = 42


def _fit(matrix):
    """Fit implicit-feedback ALS on `matrix`; return `(user_factors, item_factors)`."""
    from implicit.als import AlternatingLeastSquares

    model = AlternatingLeastSquares(
        factors=FACTORS,
        iterations=ITERATIONS,
        regularization=REGULARIZATION,
        use_gpu=False,
        random_state=SEED,
    )
    model.fit(matrix, show_progress=False)
    return np.asarray(model.user_factors), np.asarray(model.item_factors)


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """``user_factors @ item_factors.T`` over the shop catalogue."""
    if population is None:
        user_f, item_f = _fit(interaction_matrix(arena))
        return (user_f @ item_f.T).astype(np.float32)
    user_f, item_f = _fit(population.matrix)
    return project_scores(arena, population, user_f, item_f)


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
