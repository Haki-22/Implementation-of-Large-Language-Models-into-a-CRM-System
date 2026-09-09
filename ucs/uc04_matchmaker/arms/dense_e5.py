"""Dense multilingual retrieval: products as vectors, the customer as the mean of theirs (formerly arm b3).

``intfloat/multilingual-e5-base`` encodes title, category and description of every
product once (cached on disk per catalogue and language, because encoding 18 213
products takes 7 to 22 minutes of CPU); a customer is the normalised mean of the
vectors of the products bought; candidates are ranked by cosine similarity. One
encoder for both languages, so the English and Czech branches compare on the same
vector space. The same cached vectors serve the hybrid arm and any query arm.
"""

from __future__ import annotations

import hashlib
import logging

import numpy as np

from utils.paths import UC04_DIR

from ..data import Arena
from ..population import Population
from ._common import item_text

NAME = "dense_e5"
TITLE = "Dense multilingual retrieval (e5)"
DESCRIPTION = "multilingual-e5-base vectors of product texts; a customer is the mean of the products bought; cosine similarity"
FAMILY = "trained encoder / dense retrieval"
SUPPORTS_POPULATION = False

MODEL = "intfloat/multilingual-e5-base"
CACHE_DIR = UC04_DIR / "eval" / "cache"
logger = logging.getLogger(__name__)


def catalog_texts(arena: Arena) -> list[str]:
    """The e5 document strings for the catalogue in ``arena.all_asins`` order."""
    return [f"passage: {item_text(arena.catalog[a], lang=arena.lang)}" for a in arena.all_asins]


def item_embeddings(arena: Arena, *, model_name: str = MODEL) -> np.ndarray:
    """Normalised catalogue vectors, from the cache when the catalogue text is unchanged."""
    texts = catalog_texts(arena)
    digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{model_name.replace('/', '__')}-{digest}.npy"
    if path.exists():
        return np.load(path)
    from sentence_transformers import SentenceTransformer

    logger.info(
        "  %s: encoding %d products with %s (cache %s)", NAME, len(texts), model_name, path.name
    )
    model = SentenceTransformer(model_name)
    emb = model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).astype(np.float32)
    np.save(path, emb)
    return emb


def customer_vectors(arena: Arena, emb: np.ndarray) -> np.ndarray:
    """Normalised mean of the bought products' vectors, zeros for an empty history."""
    out = np.zeros((arena.n_customers, emb.shape[1]), dtype=np.float32)
    for u, c in enumerate(arena.customers):
        idx = [arena.asin_to_idx[a] for a in c.history_asins if a in arena.asin_to_idx]
        if idx:
            v = emb[idx].mean(axis=0)
            n = float(np.linalg.norm(v))
            out[u] = v / n if n > 0 else v
    return out


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Cosine similarity between each customer's mean vector and every product."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    emb = item_embeddings(arena)
    return customer_vectors(arena, emb) @ emb.T


__all__ = [
    "DESCRIPTION",
    "FAMILY",
    "MODEL",
    "NAME",
    "SUPPORTS_POPULATION",
    "TITLE",
    "catalog_texts",
    "customer_vectors",
    "item_embeddings",
    "score",
]
