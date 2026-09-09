"""The population regime: the whole Amazon Electronics 5-core dump as training data.

Decision 2026-09-06: besides the in-CRM regime (the arms learn only from the shop's
own 425 customers) the collaborative arms also run in a regime where they learn
from every reviewer in the public dump (192 403 people, 63 001 products, 1.69 M
reviews) and are then applied to the shop's customers over the shop's catalogue.
The dump is streamed straight from the committed, md5-pinned raw file the substrate
already downloads (``substrate.pipeline.data_acquisition.fetch_and_filter``); no
second database, no extra snapshot. Reading takes ~10 s, ALS trains in ~20 s.

Only arms that learn from who-bought-what can use the regime (ALS, SVD,
popularity); text arms already see the whole catalogue text in both regimes, and a
language-model arm never sees the population, so results are reported per regime
and never mixed in one table.

Leakage guard: the shop customers' hidden last purchases are removed from the
population matrix before training, exactly as they are hidden in the in-CRM
regime. Nothing else is removed: other people's later reviews of the same product
stay, as in every leave-one-out protocol.
"""

from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix

from substrate.pipeline.data_acquisition import fetch_and_filter as _raw

from .data import Arena

REVIEWS_FILE = "reviews_Electronics_5.json.gz"


@dataclass
class Population:
    """The population interaction matrix and the rows of the shop's customers in it."""

    matrix: csr_matrix  # users x items, confidence 1 + rating, held-out pairs removed
    user_index: dict[str, int]  # reviewerID -> row
    item_index: dict[str, int]  # asin -> column
    n_reviews: int
    seconds: float
    last_item: dict[int, int] = field(
        default_factory=dict
    )  # row -> column of the reviewer's latest review

    def customer_rows(self, arena: Arena) -> list[int | None]:
        """Population row of each arena customer (None if the reviewer is not in the dump)."""
        return [self.user_index.get(c.reviewer_id) for c in arena.customers]

    def shop_columns(self, arena: Arena) -> tuple[np.ndarray, list[int]]:
        """Population columns of the shop catalogue and the arena positions they belong to."""
        cols, positions = [], []
        for pos, asin in enumerate(arena.all_asins):
            j = self.item_index.get(asin)
            if j is not None:
                cols.append(j)
                positions.append(pos)
        return np.asarray(cols), positions


def raw_reviews_path():
    """The pinned raw reviews file, as the substrate step downloads it."""
    path = _raw.DATA_DIR / REVIEWS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing; fetch it with `python -m substrate.pipeline.data_acquisition.fetch_and_filter --download`"
        )
    return path


def load_population(arena: Arena) -> Population:
    """Stream the dump into a user x item matrix, with the arena customers' hidden purchases removed."""
    t0 = time.time()
    held = {(c.reviewer_id, c.held_out.asin) for c in arena.customers}
    users: dict[str, int] = {}
    items: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    latest: dict[int, tuple[int, int]] = {}  # row -> (time, column) of the newest review kept
    n = 0
    with gzip.open(raw_reviews_path(), "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            n += 1
            uid, asin = d["reviewerID"], d["asin"]
            if (uid, asin) in held:
                continue
            u = users.setdefault(uid, len(users))
            j = items.setdefault(asin, len(items))
            rows.append(u)
            cols.append(j)
            vals.append(1.0 + float(d.get("overall", 3.0)))
            ts = int(d.get("unixReviewTime", 0))
            if u not in latest or ts >= latest[u][0]:
                latest[u] = (ts, j)
    matrix = csr_matrix((vals, (rows, cols)), shape=(len(users), len(items)), dtype=np.float32)
    matrix.sum_duplicates()
    return Population(
        matrix=matrix,
        user_index=users,
        item_index=items,
        n_reviews=n,
        seconds=time.time() - t0,
        last_item={u: j for u, (_, j) in latest.items()},
    )


def project_scores(
    arena: Arena, population: Population, user_factors: np.ndarray, item_factors: np.ndarray
) -> np.ndarray:
    """Score every arena customer against the shop catalogue from population factors; ``-inf`` where unknown."""
    scores = np.full((arena.n_customers, arena.n_items), -np.inf, dtype=np.float32)
    cols, positions = population.shop_columns(arena)
    item_f = item_factors[cols]
    for u, row in enumerate(population.customer_rows(arena)):
        if row is None:
            continue
        scores[u, positions] = item_f @ user_factors[row]
    return scores


__all__ = ["Population", "load_population", "project_scores", "raw_reviews_path"]
