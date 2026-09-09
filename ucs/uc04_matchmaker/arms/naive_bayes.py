"""Naive Bayes over the history bag: P(next product | products bought) (formerly arm b17).

Multinomial naive Bayes (McCallum & Nigam 1998) adapted to recommendation: a
customer's bought products are the "words", the next product the class. Classes
are the 500 most-bought products so each has training examples; the other
products get no opinion. The simplest statistical baseline a student writes first.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
from scipy.sparse import csr_matrix

from ..data import Arena
from ..population import Population
from ._common import empty_scores

NAME = "naive_bayes"
TITLE = "Naive Bayes over the purchase history"
DESCRIPTION = (
    "multinomial naive Bayes, bought products as features, the 500 most-bought products as classes"
)
FAMILY = "classical / probabilistic"
SUPPORTS_POPULATION = False

TARGET_TOP_N = 500
ALPHA = 1.0


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Log-probability of each of the 500 target products given the customer's bag."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    from sklearn.naive_bayes import MultinomialNB

    pop: Counter[str] = Counter()
    for c in arena.customers:
        pop.update(c.history_asins)
    targets = [a for a, _ in pop.most_common(TARGET_TOP_N)]
    target_idx = {a: i for i, a in enumerate(targets)}
    rows, cols, y = [], [], []
    n = 0
    for c in arena.customers:
        hist = [a for a in c.history_asins if a in arena.asin_to_idx]
        for t in hist:
            if t not in target_idx:
                continue
            for h in hist:
                if h != t:
                    rows.append(n)
                    cols.append(arena.asin_to_idx[h])
            y.append(target_idx[t])
            n += 1
    scores = empty_scores(arena)
    if n == 0:
        return scores
    x = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(n, arena.n_items))
    model = MultinomialNB(alpha=ALPHA).fit(x, np.asarray(y))
    class_cols = [arena.asin_to_idx[targets[k]] for k in model.classes_]
    for u, c in enumerate(arena.customers):
        hist = [arena.asin_to_idx[a] for a in c.history_asins if a in arena.asin_to_idx]
        if not hist:
            continue
        q = csr_matrix(
            (np.ones(len(hist), dtype=np.float32), ([0] * len(hist), hist)),
            shape=(1, arena.n_items),
        )
        scores[u, class_cols] = model.predict_log_proba(q).ravel()
    return scores


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
