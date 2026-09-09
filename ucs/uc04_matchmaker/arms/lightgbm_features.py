"""LightGBM on engineered features: boosted trees over customer x product features (formerly arm b7).

Pointwise binary classifier (bought / not bought) on the feature table in
``_features.py``; every product is then scored for every customer. Represents
the feature-engineering school that wins tabular competitions.
"""

from __future__ import annotations

import numpy as np

from ..data import Arena
from ..population import Population
from ._features import FeatureTable

NAME = "lightgbm_features"
TITLE = "LightGBM on engineered features"
DESCRIPTION = (
    "boosted trees, bought-or-not, over category, price, length and history-overlap features"
)
FAMILY = "classical / gradient boosting"
SUPPORTS_POPULATION = False

PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 5,
    "verbose": -1,
    "seed": 42,
    # pinned threads + deterministic histograms; in this environment the arm still moves by a few
    # hits of 425 between processes (147 / 149 / 150 measured 2026-09-06), inside its interval,
    # so the card names it as the one arm that is not bit-reproducible
    "num_threads": 4,
    "deterministic": True,
    "force_row_wise": True,
}
ROUNDS = 200


def score(
    arena: Arena,
    *,
    population: Population | None = None,
    personality: dict[int, dict[str, float]] | None = None,
) -> np.ndarray:
    """Probability of purchase for every customer x product pair.

    ``personality`` (contact id -> Big Five profile) adds five customer columns; the
    recorded arm runs without it, ``personality.py`` runs the paired comparison. A
    customer missing from the mapping gets NaN, which LightGBM handles natively.
    """
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    import lightgbm as lgb

    table = FeatureTable(arena, personality=personality)
    x, y = table.training_set()
    booster = lgb.train(PARAMS, lgb.Dataset(x, label=y), num_boost_round=ROUNDS)
    return table.score_all(lambda rows: booster.predict(rows))


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
