"""How a score matrix becomes a result: the two scoring protocols and their metrics.

Every arm returns one matrix ``scores[customer, item]`` over the whole catalogue
(``-inf`` where the arm has no opinion). This module turns it into numbers under
two protocols, decided 2026-09-06 (D-UC04-1), and both are always reported:

* **full** — the hidden item is ranked against the whole shop catalogue (18 213
  products). Hit@K if it lands in the top K. This is what a shop would see; on a
  sparse catalogue and 425 heavy buyers every method scores single digits, so the
  protocol tells "above the random floor or not", never a ranking of methods.
* **sampled** — the hidden item is ranked against ``n_neg`` products the customer
  never bought, drawn once per customer with a fixed seed, the same list for every
  arm. Hit@K if it lands in the top K of those ``n_neg + 1``. Guessing scores
  ``K / (n_neg + 1)``. This is the protocol under which recommenders are compared in
  the literature and under which language models are evaluated as rankers; it is
  an easier task than the full catalogue (Krichene & Rendle 2020 show the two are not
  consistent), which the results card states next to every number.

Ties: an arm that scores nothing for some items (``-inf``) leaves them tied at the
bottom; the tie is broken by a seeded shuffle, so an arm without an opinion ranks
those items at random and cannot borrow popularity or catalogue order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .data import Arena

NEG_INF = -np.inf
KS = (5, 10)


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


def mask_history(scores: np.ndarray, arena: Arena) -> np.ndarray:
    """Return a copy with every customer's own history set to ``-inf`` (never re-recommend)."""
    out = np.array(scores, dtype=np.float32, copy=True)
    for u, c in enumerate(arena.customers):
        idx = [arena.asin_to_idx[a] for a in c.history_asins if a in arena.asin_to_idx]
        out[u, idx] = NEG_INF
    return out


def _order(row: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Indices of ``row`` from best to worst; ties (incl. ``-inf``) broken by a seeded shuffle."""
    jitter = rng.random(row.shape[0])
    return np.lexsort((jitter, -row))


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95 % interval for a binomial share."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - half) / denom, (centre + half) / denom)


@dataclass
class Result:
    """Numbers for one arm × branch × protocol, plus per-customer detail for the run folder."""

    protocol: str
    n_customers: int
    hits: dict[int, int]  # K -> hits
    per_group: dict[str, dict[str, Any]]  # group -> {"n", "hits": {K: hits}}
    ndcg10: float
    mrr10: float
    reach: dict[int, int] = field(
        default_factory=dict
    )  # K -> customers whose hidden item is in top K
    per_customer: list[dict[str, Any]] = field(default_factory=list)

    def hr(self, k: int) -> float:
        """Hit rate at `k`: the share of customers whose hidden item landed in the top `k`."""
        return self.hits[k] / self.n_customers if self.n_customers else 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary: hits, hit rates, the Wilson interval on HR@10, nDCG@10, MRR@10, per-group and reach."""
        d: dict[str, Any] = {
            "protocol": self.protocol,
            "n_customers": self.n_customers,
            "hits": {str(k): v for k, v in self.hits.items()},
            "hr": {str(k): self.hr(k) for k in self.hits},
            "wilson95_hr10": wilson(self.hits.get(10, 0), self.n_customers),
            "ndcg@10": self.ndcg10,
            "mrr@10": self.mrr10,
            "per_group": self.per_group,
        }
        if self.reach:
            d["reach"] = {str(k): v for k, v in self.reach.items()}
        return d


def _summarise(
    protocol: str,
    arena: Arena,
    ranks: list[int | None],
    top_lists: list[list[str]],
    reach_ks: tuple[int, ...] = (),
) -> Result:
    """Aggregate per-customer ranks (1-based position of the hidden item, None = beyond the list)."""
    hits = {k: 0 for k in KS}
    per_group: dict[str, dict[str, Any]] = {}
    ndcg = mrr = 0.0
    reach = {k: 0 for k in reach_ks}
    detail: list[dict[str, Any]] = []
    for c, r, top in zip(arena.customers, ranks, top_lists):
        g = per_group.setdefault(c.group, {"n": 0, "hits": {k: 0 for k in KS}})
        g["n"] += 1
        for k in KS:
            if r is not None and r <= k:
                hits[k] += 1
                g["hits"][k] += 1
        if r is not None and r <= 10:
            ndcg += 1.0 / math.log2(r + 1)
            mrr += 1.0 / r
        for k in reach_ks:
            if r is not None and r <= k:
                reach[k] += 1
        detail.append(
            {
                "contact_id": c.contact_id,
                "group": c.group,
                "held_out": c.held_out.asin,
                "rank": r,
                "top10": top[:10],
            }
        )
    n = len(arena.customers)
    for g in per_group.values():
        g["hr"] = {str(k): (g["hits"][k] / g["n"] if g["n"] else 0.0) for k in KS}
        g["hits"] = {str(k): v for k, v in g["hits"].items()}
    return Result(
        protocol=protocol,
        n_customers=n,
        hits=hits,
        per_group=per_group,
        ndcg10=ndcg / n if n else 0.0,
        mrr10=mrr / n if n else 0.0,
        reach=reach,
        per_customer=detail,
    )


# ---------------------------------------------------------------------------
# Protocol 1: the whole catalogue
# ---------------------------------------------------------------------------


def evaluate_full(
    scores: np.ndarray,
    arena: Arena,
    *,
    seed: int = 42,
    reach_ks: tuple[int, ...] = (30, 200),
    keep_top: int = 200,
) -> Result:
    """Rank the hidden item against the whole catalogue; ``reach_ks`` records how often it sits within the top K (the ceiling of a re-ranker over that list)."""
    masked = mask_history(scores, arena)
    rng = np.random.default_rng(seed)
    ranks: list[int | None] = []
    tops: list[list[str]] = []
    for u, c in enumerate(arena.customers):
        order = _order(masked[u], rng)
        # A customer's own purchases leave the ranking entirely: with an arm that has no
        # opinion on most products they would otherwise be shuffled among the unscored ones.
        hist = np.fromiter(
            (arena.asin_to_idx[a] for a in c.history_asins if a in arena.asin_to_idx), dtype=np.int64
        )
        if hist.size:
            order = order[~np.isin(order, hist)]
        target = arena.asin_to_idx.get(c.held_out.asin)
        pos = int(np.nonzero(order == target)[0][0]) + 1 if target is not None else None
        ranks.append(pos)
        tops.append([arena.all_asins[int(j)] for j in order[:keep_top]])
    return _summarise("full", arena, ranks, tops, reach_ks)


# ---------------------------------------------------------------------------
# Protocol 2: the hidden item among sampled unbought items
# ---------------------------------------------------------------------------


def sample_candidates(arena: Arena, *, n_neg: int = 100, seed: int = 42) -> list[list[int]]:
    """Per customer: ``n_neg`` catalogue indices the customer never bought plus the hidden item, fixed by ``seed``.

    Drawn per contact id so the list is stable across arms, runs and branches.
    """
    out: list[list[int]] = []
    n_items = arena.n_items
    for c in arena.customers:
        rng = np.random.default_rng([seed, c.contact_id])
        forbidden = {arena.asin_to_idx[a] for a in c.history_asins if a in arena.asin_to_idx}
        target = arena.asin_to_idx[c.held_out.asin]
        forbidden.add(target)
        picked: list[int] = []
        while len(picked) < n_neg:
            j = int(rng.integers(0, n_items))
            if j in forbidden:
                continue
            forbidden.add(j)
            picked.append(j)
        picked.append(target)
        out.append(picked)
    return out


def evaluate_sampled(
    scores: np.ndarray, arena: Arena, candidates: list[list[int]], *, seed: int = 42
) -> Result:
    """Rank the hidden item against its sampled negatives only; the same candidate lists for every arm."""
    rng = np.random.default_rng(seed)
    ranks: list[int | None] = []
    tops: list[list[str]] = []
    for u, (c, cand) in enumerate(zip(arena.customers, candidates)):
        cand_arr = np.asarray(cand)
        row = scores[u, cand_arr].astype(np.float32)
        order = _order(row, rng)
        target_pos = len(cand) - 1  # the hidden item is appended last by sample_candidates
        pos = int(np.nonzero(order == target_pos)[0][0]) + 1
        ranks.append(pos)
        tops.append([arena.all_asins[int(cand_arr[j])] for j in order[:10]])
    return _summarise("sampled", arena, ranks, tops)


def random_floor(protocol: str, n_items: int, n_neg: int, k: int = 10) -> float:
    """Hit rate of guessing under each protocol."""
    return k / n_items if protocol == "full" else k / (n_neg + 1)


__all__ = [
    "KS",
    "NEG_INF",
    "Result",
    "evaluate_full",
    "evaluate_sampled",
    "mask_history",
    "random_floor",
    "sample_candidates",
    "wilson",
]
