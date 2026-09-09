"""BM25 keyword search: the customer's review words as a query against product texts (formerly arm b2).

Content-based recommendation by lexical similarity. The query is the 200 most
frequent tokens of everything the customer wrote (review text and headlines) plus
the texts of the products bought; the documents are title, category and
description of every product. In the Czech branch the tokens are lemmatised with
``simplemma`` so inflected forms match. The retrieval itself works (a product
queried by its own title comes back first for 26 of 30 tries, all 30 in the top
10); its zero in the full-catalogue protocol therefore means that what customers
write about does not lexically name what they buy next.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np

from ..data import Arena
from ..population import Population
from ._common import item_text

NAME = "bm25_text"
TITLE = "BM25 keyword search"
DESCRIPTION = "the customer's 200 most frequent review words (lemmatised in Czech) against product title, category and description"
FAMILY = "classical / lexical retrieval"
SUPPORTS_POPULATION = False

TOP_TERMS = 200
_TOKEN = re.compile(r"[A-Za-zÁ-ž0-9]{2,}")


def tokens(text: str, lang: str) -> list[str]:
    """Lower-cased tokens; Czech is lemmatised when ``simplemma`` is installed."""
    raw = [t.lower() for t in _TOKEN.findall(text)]
    if lang == "cs":
        try:
            import simplemma

            return [simplemma.lemmatize(t, lang="cs") for t in raw]
        except ImportError:
            return raw
    return raw


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """BM25 score of every product for every customer's query (0 where no term matches)."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    from rank_bm25 import BM25Okapi

    docs = [tokens(item_text(arena.catalog[a], lang=arena.lang), arena.lang) for a in arena.all_asins]
    index = BM25Okapi(docs)
    scores = np.zeros((arena.n_customers, arena.n_items), dtype=np.float32)
    for u, c in enumerate(arena.customers):
        parts = []
        for it in c.history:
            parts.append(it.summary)
            parts.append(it.text)
            parts.append(item_text(arena.catalog.get(it.asin, {}), lang=arena.lang))
        toks = tokens(" ".join(parts), arena.lang)
        if not toks:
            continue
        query = [t for t, _ in Counter(toks).most_common(TOP_TERMS)]
        scores[u] = np.asarray(index.get_scores(query), dtype=np.float32)
    return scores


__all__ = ["DESCRIPTION", "FAMILY", "NAME", "SUPPORTS_POPULATION", "TITLE", "score", "tokens"]
