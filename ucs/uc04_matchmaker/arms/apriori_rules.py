"""Apriori association rules: "who bought X also bought Y" (formerly arm b9).

Each customer's history is a basket; frequent pairs with support >= 0.006 among
the 2 000 most-bought products give rules antecedent -> consequent scored by lift
x confidence; a candidate's score is the sum over the rules its antecedents in the
customer's history fire. Products no rule reaches get no opinion (``-inf``), so
the arm cannot borrow popularity. The method the opponent teaches (CRISP-DM course
material) and the link from the arena back to chapter 2.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from ..data import Arena
from ..population import Population
from ._common import empty_scores

NAME = "apriori_rules"
TITLE = "Apriori association rules"
DESCRIPTION = "frequent product pairs (support 0.006, top-2 000 products) as rules scored by lift x confidence"
FAMILY = "classical / association rules"
SUPPORTS_POPULATION = False

MIN_SUPPORT = 0.006
TOP_ITEMS = 2000
MAX_ITEMSET_LEN = 2
MIN_CONFIDENCE = 0.05
logger = logging.getLogger(__name__)


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Sum of rule scores over the rules a customer's history fires; ``-inf`` elsewhere."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    from mlxtend.frequent_patterns import apriori, association_rules
    from mlxtend.preprocessing import TransactionEncoder

    freq_items: Counter[str] = Counter()
    for c in arena.customers:
        freq_items.update(c.history_asins)
    top_items = {a for a, _ in freq_items.most_common(TOP_ITEMS)}
    baskets = [[a for a in c.history_asins if a in top_items] for c in arena.customers]
    baskets = [b for b in baskets if b]
    scores = empty_scores(arena)
    if not baskets:
        return scores
    encoder = TransactionEncoder()
    frame = pd.DataFrame(encoder.fit_transform(baskets), columns=encoder.columns_)
    frequent = apriori(frame, min_support=MIN_SUPPORT, max_len=MAX_ITEMSET_LEN, use_colnames=True)
    if frequent.empty:
        return scores
    rules = association_rules(frequent, metric="confidence", min_threshold=MIN_CONFIDENCE)
    logger.info("  %s: %d frequent itemsets, %d rules", NAME, len(frequent), len(rules))
    index: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for _, row in rules.iterrows():
        weight = float(row["lift"]) * float(row["confidence"])
        for a in row["antecedents"]:
            for b in row["consequents"]:
                index[a].append((b, weight))
    for u, c in enumerate(arena.customers):
        fired: dict[str, float] = defaultdict(float)
        for a in c.history_asins:
            for b, w in index.get(a, ()):
                fired[b] += w
        for b, w in fired.items():
            j = arena.asin_to_idx.get(b)
            if j is not None:
                scores[u, j] = w
    return scores


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
