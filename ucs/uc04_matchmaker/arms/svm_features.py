"""Linear SVM on engineered features: the linear check on the LightGBM arm (formerly arm b16).

Same feature table, same positives and negatives, a linear classifier instead of
trees; its only job is to show whether the tree model wins by non-linearity.
"""

from __future__ import annotations

import numpy as np

from ..data import Arena
from ..population import Population
from ._features import MIDPOINT, FeatureTable

NAME = "svm_features"
TITLE = "Linear SVM on engineered features"
DESCRIPTION = "linear SVM, bought-or-not, over the same features as the LightGBM arm"
FAMILY = "classical / linear"
SUPPORTS_POPULATION = False


def score(
    arena: Arena,
    *,
    population: Population | None = None,
    personality: dict[int, dict[str, float]] | None = None,
) -> np.ndarray:
    """Signed distance to the separating plane for every customer x product pair.

    ``personality`` as in the LightGBM arm; a customer missing from the mapping gets
    the scale midpoint (3.0 of 5), because a linear model cannot take NaN.
    """
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC

    table = FeatureTable(arena, personality=personality, missing=MIDPOINT)
    x, y = table.training_set()
    model = make_pipeline(
        StandardScaler(), LinearSVC(C=0.5, class_weight="balanced", max_iter=5000)
    )
    model.fit(x, y)
    return table.score_all(lambda rows: model.decision_function(rows))


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
