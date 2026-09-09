"""Adamic-Adar link prediction on the customer-product graph (formerly arm b15).

Customers and products are nodes, purchases are edges. A candidate product scores
the sum, over the products j in the customer's history that other customers also
bought, of ``1 / log(deg(j))`` for every co-buyer of j who also bought the
candidate; popular bridge products count less (Adamic & Adar 2003). Products no
co-buyer reaches get no opinion.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from ..data import Arena
from ..population import Population
from ._common import empty_scores

NAME = "adamic_adar"
TITLE = "Adamic-Adar link prediction"
DESCRIPTION = "co-buyer paths through the customer-product graph, weighted 1 / log(degree)"
FAMILY = "classical / graph"
SUPPORTS_POPULATION = False


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Adamic-Adar index between each customer and every product reachable through a co-buyer."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    buyers: dict[str, set[int]] = defaultdict(set)
    for u, c in enumerate(arena.customers):
        for a in c.history_asins:
            buyers[a].add(u)
    weight = {a: 1.0 / math.log(len(us)) for a, us in buyers.items() if len(us) >= 2}
    scores = empty_scores(arena)
    for u, c in enumerate(arena.customers):
        acc: dict[str, float] = defaultdict(float)
        for j in c.history_asins:
            w = weight.get(j)
            if w is None:
                continue
            for v in buyers[j]:
                if v == u:
                    continue
                for cand in arena.customers[v].history_asins:
                    if cand != j and cand not in c.history_asins:
                        acc[cand] += w
        for cand, s in acc.items():
            scores[u, arena.asin_to_idx[cand]] = s
    return scores


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
