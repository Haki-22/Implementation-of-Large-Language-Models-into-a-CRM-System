"""The engineered feature table shared by the LightGBM and SVM arms.

Customer features: number of purchases, mean rating, stratum. Product features:
one-hot of the 30 most common categories, title and description length. Pair
feature: category overlap between the customer's history and the product.

Personality (optional): five more customer columns, the Big Five profile scaled to
0-1, when ``personality`` maps contact ids to profiles. The recorded arms run without
it (``personality=None``): the profile was removed from them on 2026-09-06 (morning)
because an inferred one existed for 62 of the 425 customers and the sampled profile
of the substrate is not a measurement. Since the rerun the same evening every linked
customer carries an inferred profile, and ``personality.py`` runs the paired comparison
(inferred / sampled / none) as its own experiment; a customer without a profile in the
given mapping gets ``missing`` (NaN for LightGBM, which handles it natively; the scale
midpoint for the SVM, which cannot).
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from ..data import Arena, Customer

TOP_CATEGORIES = 30
NEG_PER_POS = 5
SEED = 42
GROUPS = ("A", "B", "C")
TRAITS = ("O", "C", "E", "A", "N")
MIDPOINT = 3.0 / 5.0  # the neutral profile on the 0-1 scale of the columns


class FeatureTable:
    """Builds customer, product and pair features for one arena."""

    def __init__(
        self,
        arena: Arena,
        *,
        personality: dict[int, dict[str, float]] | None = None,
        missing: float = np.nan,
    ) -> None:
        """Precompute the top-category vocabulary and the per-product feature matrix for `arena`."""
        self.arena = arena
        self.personality = personality
        self.missing = missing
        counts = Counter(
            str(cat) for meta in arena.catalog.values() for cat in meta.get("categories") or []
        )
        self.top_cats = [c for c, _ in counts.most_common(TOP_CATEGORIES)]
        cat_idx = {c: i for i, c in enumerate(self.top_cats)}
        n = arena.n_items
        self.item_matrix = np.zeros((n, TOP_CATEGORIES + 2), dtype=np.float32)
        self.item_cats: list[set[str]] = []
        for j, asin in enumerate(arena.all_asins):
            meta = arena.catalog[asin]
            cats = {str(c) for c in meta.get("categories") or []}
            self.item_cats.append(cats)
            for c in cats:
                if c in cat_idx:
                    self.item_matrix[j, cat_idx[c]] = 1.0
            self.item_matrix[j, TOP_CATEGORIES] = len(meta.get("title") or "") / 100.0
            self.item_matrix[j, TOP_CATEGORIES + 1] = len(meta.get("description") or "") / 1000.0

    def customer_vector(self, c: Customer) -> tuple[np.ndarray, set[str]]:
        """`c`'s feature vector (purchase count, mean rating, group one-hot, optional personality) and its history categories."""
        ratings = [it.rating for it in c.history]
        vec = np.zeros(2 + len(GROUPS), dtype=np.float32)
        vec[0] = len(c.history) / 100.0
        vec[1] = (float(np.mean(ratings)) if ratings else 3.0) / 5.0
        if c.group in GROUPS:
            vec[2 + GROUPS.index(c.group)] = 1.0
        if self.personality is not None:
            profile = self.personality.get(c.contact_id)
            traits = (
                np.array([float(profile[t]) / 5.0 for t in TRAITS], dtype=np.float32)
                if profile
                else np.full(len(TRAITS), self.missing, dtype=np.float32)
            )
            vec = np.concatenate([vec, traits])
        hist_cats: set[str] = set()
        for a in c.history_asins:
            j = self.arena.asin_to_idx.get(a)
            if j is not None:
                hist_cats |= self.item_cats[j]
        return vec, hist_cats

    def overlap(self, hist_cats: set[str]) -> np.ndarray:
        """Per-product category overlap with `hist_cats`, one value per catalogue item."""
        return np.array([len(hist_cats & cats) / 10.0 for cats in self.item_cats], dtype=np.float32)

    def rows_for(self, c: Customer, item_idx: np.ndarray) -> np.ndarray:
        """Pair features for one customer and the given product indices."""
        vec, hist_cats = self.customer_vector(c)
        overlap = self.overlap(hist_cats)[item_idx]
        return np.hstack(
            [np.tile(vec, (len(item_idx), 1)), self.item_matrix[item_idx], overlap[:, None]]
        )

    def training_set(self) -> tuple[np.ndarray, np.ndarray]:
        """Bought products as positives, ``NEG_PER_POS`` random unbought products per positive as negatives."""
        rng = np.random.default_rng(SEED)
        xs, ys = [], []
        n = self.arena.n_items
        for c in self.arena.customers:
            pos = np.array(
                [self.arena.asin_to_idx[a] for a in c.history_asins if a in self.arena.asin_to_idx]
            )
            if pos.size == 0:
                continue
            neg = rng.choice(n, size=min(len(pos) * NEG_PER_POS, n - len(pos)), replace=False)
            neg = neg[~np.isin(neg, pos)]
            xs.append(self.rows_for(c, pos))
            ys.append(np.ones(len(pos)))
            xs.append(self.rows_for(c, neg))
            ys.append(np.zeros(len(neg)))
        return np.vstack(xs), np.concatenate(ys)

    def score_all(self, predict) -> np.ndarray:
        """Score every product for every customer with ``predict(rows) -> scores``."""
        all_idx = np.arange(self.arena.n_items)
        out = np.zeros((self.arena.n_customers, self.arena.n_items), dtype=np.float32)
        for u, c in enumerate(self.arena.customers):
            out[u] = np.asarray(predict(self.rows_for(c, all_idx)), dtype=np.float32)
        return out


__all__ = ["MIDPOINT", "TRAITS", "FeatureTable", "NEG_PER_POS", "TOP_CATEGORIES"]
