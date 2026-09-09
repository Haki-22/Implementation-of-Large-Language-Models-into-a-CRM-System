"""Pieces every arm shares: the interaction matrix, the score matrix shape, text of an item.

An arm is a module with ``NAME`` (the slug used in commands, registries and run
folders), ``TITLE`` (what the method is, e.g. "ALS collaborative filtering"),
``DESCRIPTION`` (one line the card prints), ``FAMILY`` and a function
``score(arena, *, population=None) -> np.ndarray`` returning ``float32``
``[n_customers, n_items]`` over ``arena.all_asins``, ``-inf`` where the arm has no
opinion. The harness masks each customer's own history and applies both protocols
(``protocols.py``); arms never rank or truncate themselves.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.sparse import csr_matrix

from ..data import Arena

NEG_INF = -np.inf


def empty_scores(arena: Arena) -> np.ndarray:
    """A score matrix with no opinion anywhere."""
    return np.full((arena.n_customers, arena.n_items), NEG_INF, dtype=np.float32)


def interaction_matrix(arena: Arena, *, confidence: bool = True) -> csr_matrix:
    """Customers x items from the histories (the hidden item is not in them by construction).

    ``confidence=True`` weights a purchase by ``1 + rating`` (implicit-feedback
    confidence, as ALS expects); ``False`` stores the raw rating (explicit
    factorisation, as SVD expects).
    """
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    for u, c in enumerate(arena.customers):
        seen: set[int] = set()
        for it in c.history:
            j = arena.asin_to_idx.get(it.asin)
            if j is None or j in seen:
                continue
            seen.add(j)
            rows.append(u)
            cols.append(j)
            vals.append(1.0 + it.rating if confidence else it.rating)
    return csr_matrix(
        (vals, (rows, cols)), shape=(arena.n_customers, arena.n_items), dtype=np.float32
    )


def item_text(meta: dict[str, Any], *, lang: str = "en", max_description: int = 400) -> str:
    """Title, category and the start of the description as one string for text arms.

    In the Czech branch the title is the Czech one where it exists (D-UC04-D); the
    description stays English, which the results card states.
    """
    title = (
        meta.get("title_cs") if lang == "cs" and meta.get("title_cs") else meta.get("title") or ""
    ).strip()
    cats = " / ".join(str(c) for c in meta.get("categories") or [])
    desc = (meta.get("description") or "").strip()[:max_description]
    parts = [p for p in (title, cats, desc) if p]
    return ". ".join(parts) if parts else str(meta.get("asin", "unknown product"))


def minmax_rows(scores: np.ndarray) -> np.ndarray:
    """Scale every row to [0, 1]; ``-inf`` entries stay ``-inf``; constant rows become 0."""
    finite = np.where(np.isfinite(scores), scores, np.nan)
    lo = np.nanmin(finite, axis=1, keepdims=True)
    hi = np.nanmax(finite, axis=1, keepdims=True)
    span = np.where(hi - lo > 1e-9, hi - lo, 1.0)
    out = (finite - lo) / span
    out = np.where(np.isnan(out), NEG_INF, out)
    return out.astype(np.float32)


__all__ = ["NEG_INF", "empty_scores", "interaction_matrix", "item_text", "minmax_rows"]
