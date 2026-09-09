"""ALS + dense hybrid: the strongest purely classical combination (formerly arm b5).

Per-customer min-max scaling of the ALS scores and the dense-retrieval scores,
then an equal-weight sum. No language model anywhere: this is the opponent every
model arm has to beat before the chapter may speak of a benefit.
"""

from __future__ import annotations

import numpy as np

from ..data import Arena
from ..population import Population
from . import als_cf, dense_e5
from ._common import minmax_rows

NAME = "hybrid_als_dense"
TITLE = "ALS + dense hybrid"
DESCRIPTION = "equal-weight sum of per-customer min-max scaled ALS and dense-retrieval scores"
FAMILY = "classical / hybrid"
SUPPORTS_POPULATION = False

WEIGHT_ALS = 0.5


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """``0.5 * minmax(ALS) + 0.5 * minmax(dense)``."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    a = minmax_rows(als_cf.score(arena))
    d = minmax_rows(dense_e5.score(arena))
    return (WEIGHT_ALS * a + (1.0 - WEIGHT_ALS) * d).astype(np.float32)


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
