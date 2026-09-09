"""Interest topics per customer: LDA over the catalogue titles, aggregated over the purchase history. Classical, no model.

Latent Dirichlet Allocation (Blei, Ng and Jordan 2003) is fitted once on the catalogue,
one document per product: the Czech title where the catalogue has one (16 067 of 18 213),
the English title otherwise, plus the category. The vendored Czech stop-list of the
substrate (``substrate/data/cz_stopwords.txt``) and scikit-learn's English list drop the
function words of both languages. A customer's topic distribution is the sum over the
products bought; the top topics come out as a label of the topic's five strongest words,
a weight, and up to five bought titles the topic covers most. Labels are therefore in the
language of the titles, mostly Czech, which is what a Czech message can name.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from substrate.pipeline.build_substrate_db import CZECH_STOPWORDS

from ..data import Arena
from . import inputs

logger = logging.getLogger(__name__)

N_TOPICS = 30
TOP_WORDS = 5
TOP_TOPICS = 5
SEED = 42


def catalogue_documents(arena: Arena) -> list[str]:
    """One document per product in ``arena.all_asins`` order: title (Czech where present) and category."""
    docs = []
    for asin in arena.all_asins:
        meta = arena.catalog[asin]
        cats = " ".join(str(c) for c in meta.get("categories") or [])
        docs.append(f"{inputs.title_of(arena.catalog, asin)} {cats}")
    return docs


def fit(
    arena: Arena, *, n_topics: int = N_TOPICS, seed: int = SEED
) -> tuple[np.ndarray, dict[int, str]]:
    """Fit LDA on the catalogue; returns the document-topic matrix and the label per topic."""
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

    docs = catalogue_documents(arena)
    stop = sorted(set(ENGLISH_STOP_WORDS) | set(CZECH_STOPWORDS))
    small = len(docs) < 200  # a toy catalogue: keep every word and fewer topics
    n_topics = min(n_topics, max(2, len(docs) // 2)) if small else n_topics
    vectorizer = CountVectorizer(
        stop_words=stop,
        max_df=1.0 if small else 0.7,
        min_df=1 if small else 5,
        max_features=5000,
        lowercase=True,
    )
    x = vectorizer.fit_transform(docs)
    vocab = vectorizer.get_feature_names_out()
    logger.info(
        "  topics: LDA over %d products, vocabulary %d, %d topics", len(docs), len(vocab), n_topics
    )
    lda = LatentDirichletAllocation(
        n_components=n_topics, learning_method="batch", random_state=seed, max_iter=20, n_jobs=4
    )
    doc_topic = lda.fit_transform(x)
    labels = {
        tid: " / ".join(vocab[i] for i in comp.argsort()[: -TOP_WORDS - 1 : -1])
        for tid, comp in enumerate(lda.components_)
    }
    return doc_topic, labels


def per_customer(
    arena: Arena, doc_topic: np.ndarray, labels: dict[int, str], *, top: int = TOP_TOPICS
) -> dict[int, list[dict[str, Any]]]:
    """Contact id -> its top topics (label, weight, evidence titles), from the whole purchase history."""
    out: dict[int, list[dict[str, Any]]] = {}
    for customer in arena.customers:
        idx = [arena.asin_to_idx[a] for a in customer.history_asins if a in arena.asin_to_idx]
        if not idx:
            out[customer.contact_id] = []
            continue
        dist = doc_topic[idx].sum(axis=0)
        dist = dist / (dist.sum() or 1.0)
        rows = []
        for tid in dist.argsort()[::-1][:top]:
            # the bought products the topic covers most, by their own probability for it
            covered = sorted(idx, key=lambda j: -doc_topic[j, tid])[:5]
            evidence = [
                inputs.title_of(arena.catalog, arena.all_asins[j])[:80]
                for j in covered
                if doc_topic[j, tid] > 0
            ]
            rows.append(
                {
                    "label": labels[int(tid)],
                    "weight": round(float(dist[tid]), 3),
                    "evidence_titles": evidence,
                    "_paradigm": "lda",
                }
            )
        out[customer.contact_id] = rows
    return out


__all__ = ["N_TOPICS", "TOP_TOPICS", "catalogue_documents", "fit", "per_customer"]
