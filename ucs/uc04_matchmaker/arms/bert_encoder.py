"""BERT encoders as recommenders: pretrained, not trained for the task (formerly arm b10).

Same construction as the dense arm but with a plain masked-language-model
encoder per language, DistilBERT for English and Czert-B for Czech, [CLS]-pooled
and never fine-tuned. The one arm with a Czech-trained model; it shows what a
language-specific encoder without task training is worth on a behavioural task.
Encoding the catalogue takes ~20 minutes per model; the vectors are cached like
the dense arm's.
"""

from __future__ import annotations

import hashlib
import logging
import os

import numpy as np

from ..data import Arena
from ..population import Population
from ._common import item_text
from .dense_e5 import CACHE_DIR, customer_vectors

NAME = "bert_encoder"
TITLE = "BERT encoders as recommenders"
DESCRIPTION = "[CLS] vectors of product texts from DistilBERT (en) or Czert-B (cs), no fine-tuning; cosine to the customer's mean vector"
FAMILY = "trained encoder / no task training"
SUPPORTS_POPULATION = False

MODELS = {"en": "distilbert-base-uncased", "cs": "UWB-AIR/Czert-B-base-cased"}
BATCH = 32
MAX_LEN = 128
logger = logging.getLogger(__name__)


def _encode(texts: list[str], model_name: str) -> np.ndarray:
    """Batch-encode `texts` with `model_name`; return L2-normalised `[CLS]`-token vectors."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    device = torch.device(
        os.environ.get("UC04_BERT_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    )
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device).eval()
    out = []
    with torch.no_grad():
        for start in range(0, len(texts), BATCH):
            enc = tok(
                texts[start : start + BATCH],
                truncation=True,
                max_length=MAX_LEN,
                padding=True,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            cls = (
                model(**enc, return_dict=True)
                .last_hidden_state[:, 0, :]
                .cpu()
                .numpy()
                .astype(np.float32)
            )
            norms = np.linalg.norm(cls, axis=1, keepdims=True)
            out.append(cls / np.where(norms > 0, norms, 1.0))
    return np.concatenate(out, axis=0)


def item_embeddings(arena: Arena) -> np.ndarray:
    """Cached [CLS] vectors of the catalogue for the branch's model."""
    model_name = MODELS[arena.lang]
    texts = [
        item_text(arena.catalog[a], lang=arena.lang, max_description=200) for a in arena.all_asins
    ]
    digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{model_name.replace('/', '__')}-{digest}.npy"
    if path.exists():
        return np.load(path)
    logger.info("  %s: encoding %d products with %s", NAME, len(texts), model_name)
    emb = _encode(texts, model_name)
    np.save(path, emb)
    return emb


def score(arena: Arena, *, population: Population | None = None) -> np.ndarray:
    """Cosine similarity between each customer's mean [CLS] vector and every product."""
    if population is not None:
        raise ValueError(f"{NAME} does not learn from the population regime")
    emb = item_embeddings(arena)
    return customer_vectors(arena, emb) @ emb.T


__all__ = ["DESCRIPTION", "FAMILY", "MODELS", "NAME", "SUPPORTS_POPULATION", "TITLE", "score"]
