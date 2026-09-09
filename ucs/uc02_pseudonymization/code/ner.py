"""NER layer of UC-02: PERSON / ORG / ADDRESS / DATE spans for Czech text.

One backend is the production default (``DEFAULT_NER_BACKEND``); the others stay
selectable so the detection table can compare them. A backend that cannot load
raises: masking silently with a weaker model, or with no NER at all, would let
names and addresses through, and the caller must know.

Backends:
    ``bardsai``   bardsai/eu-pii-anonimization-multilang, XLM-RoBERTa fine-tuned on
                  EU PII categories, ONNX INT8 on CPU (Apache 2.0).
    ``gliner``    knowledgator/gliner-x-large, open-vocabulary NER; the labels are
                  passed at inference time (Apache 2.0; see NOTICE.md for current model terms).
    ``richielo``  richielo/small-e-czech-finetuned-ner-wikiann, Czech ELECTRA with
                  PER / ORG / LOC only (CC BY 4.0).
    ``presidio``  Microsoft Presidio with Czech pattern recognisers, the industry
                  baseline (``ner_presidio.py``).

Every span carries ``source = "ner:<backend>"`` so a mapping records which model
produced it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backends and label maps
# ---------------------------------------------------------------------------

# The production backend = the winner of the detection table on the corpus of
# record among licences a CRM vendor could use (D-UC02-3). Table of 2026-09-05
# on the model-rendered record (eval/runs/2026-09-05-detection-table-model-corpus-23-configs, strict F1
# with the rules): bardsai 1.000, bardsai_v2 0.984, stulcrad 0.974, wismut
# 0.974, bardsai_mini 0.968, wismut_small 0.950, gliner2 0.869, gliner 0.792,
# snerta 0.774, richielo 0.734, presidio 0.382. See eval/NER-COMPARISON.md.
DEFAULT_NER_BACKEND = "bardsai"

PRIMARY_MODEL = "bardsai/eu-pii-anonimization-multilang"
FALLBACK_MODEL = "richielo/small-e-czech-finetuned-ner-wikiann"
GLINER_MODEL = "knowledgator/gliner-x-large"

# Candidates from the 2026-09-05 landscape scan (D-UC02-3), each a HuggingFace
# token-classification checkpoint loaded through one generic loader whose labels
# go through ``label_to_type``; ``gliner2`` is the open-vocabulary GLiNER 2.5
# through its own package. A revision pins a rolling checkpoint.
CANDIDATE_MODELS: dict[str, dict[str, str | None]] = {
    "bardsai_v2": {
        "model": "bardsai/eu-pii-anonimization-multilang-v2-preview",
        "revision": "8e0b19766bb0dd4916d096b4f540dd46c138c760",
        "note": "successor of the production model, rolling preview pinned to 2026-06-11",
    },
    "bardsai_mini": {
        "model": "bardsai/eu-pii-multi-mini-preview",
        "revision": None,
        "note": "107M sibling, licence not stated on the card: smoke only",
    },
    "wismut": {
        "model": "Wismut/nym-pii-multilingual",
        "revision": None,
        "note": "mmBERT-base PII tagger, MIT, names Czech",
    },
    "wismut_small": {
        "model": "Wismut/nym-pii-multilingual-small",
        "revision": None,
        "onnx_file": "model.onnx",
        "note": "16-layer variant of wismut; the repo ships ONNX weights only",
    },
    "snerta": {
        "model": "ivlcic/snerta-12l-base",
        "revision": None,
        "note": "mDeBERTa Slavic NER trained partly on CNEC 2.0; no DATE label",
    },
    "stulcrad": {
        "model": "stulcrad/CNEC2_0_Supertypes_xlm-roberta-large",
        "revision": None,
        "note": "Czech-only CNEC 2.0 supertypes; corpus is non-commercial",
    },
}
GLINER2_MODEL = "fastino/gliner2.5-multi-v1"

NER_BACKENDS: tuple[str, ...] = (
    "bardsai",
    "gliner",
    "richielo",
    "presidio",
    *CANDIDATE_MODELS,
    "gliner2",
)

# Backend licences from the 2026-09-05 scan; GLiNER corrected against its card on 2026-09-09.
# A CRM vendor reads this column before the F1 column.
LICENCES: dict[str, str] = {
    "bardsai": "Apache 2.0",
    "gliner": "Apache 2.0",
    "richielo": "CC BY 4.0",
    "presidio": "MIT",
    "bardsai_v2": "Apache 2.0 (rolling preview, pinned)",
    "bardsai_mini": "not stated on the card",
    "wismut": "MIT",
    "wismut_small": "MIT",
    "snerta": "Apache 2.0 (source-corpus terms apply)",
    "stulcrad": "MIT tag; CNEC 2.0 corpus CC BY-NC-SA",
    "gliner2": "Apache 2.0",
    "nametag3": "CC BY-NC-SA 4.0",
}

# backend -> model id, for the provenance record of a run
MODEL_IDS: dict[str, str] = {
    "bardsai": PRIMARY_MODEL,
    "gliner": GLINER_MODEL,
    "richielo": FALLBACK_MODEL,
    "gliner2": GLINER2_MODEL,
    **{name: str(spec["model"]) for name, spec in CANDIDATE_MODELS.items()},
}

# bardsai EU-PII label -> canonical type
_BARDSAI_LABEL_MAP: dict[str, str] = {
    "PERSON_NAME": "PERSON",
    "PERSON_ALIAS": "PERSON",
    "PROPER_NAME": "PERSON",
    "ORGANIZATION_NAME": "ORG",
    "POSTAL_ADDRESS": "ADDRESS",
    "LOCATION": "ADDRESS",
    "GEO_LOCATION": "ADDRESS",
    "DATE": "DATE",
    "DATE_OF_BIRTH": "DATE",
}

# richielo / WikiAnn label -> canonical type
_RICHIELO_LABEL_MAP: dict[str, str] = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORG",
    "LOC": "ADDRESS",
}

# GLiNER is open-vocabulary: the canonical types are the labels.
_GLINER_LABELS = ("PERSON", "ORG", "ADDRESS", "DATE")

# GLiNER 2.5 takes label strings at inference; these four map to the canonical types.
_GLINER2_LABELS: dict[str, str] = {
    "person name": "PERSON",
    "organization name": "ORG",
    "postal address": "ADDRESS",
    "date": "DATE",
}

# One label normaliser for every candidate checkpoint. The label sets differ
# (bardsai families, Wismut's address parts, snerta's PER/LOC/ORG/MISC, the CNEC
# supertypes P/G/I/T/A); everything that is a person, an organisation, a place or
# address part, or a date maps to the four canonical types, and everything else
# (format identifiers the rules cover, MISC, artifacts) is dropped.
_PERSON_LABELS = frozenset(
    {
        "PER", "PERSON", "P", "PS", "PF", "PERSON_NAME", "PERSON_ALIAS", "PROPER_NAME",
        "GIVEN_NAME", "SURNAME", "FIRST_NAME", "LAST_NAME", "FULL_NAME", "NAME",
        "MIDDLE_NAME", "PERSON_FIRST_NAME", "PERSON_LAST_NAME",
    }
)  # fmt: skip
_ORG_LABELS = frozenset(
    {
        "ORG", "ORGANIZATION", "ORGANISATION", "ORGANIZATION_NAME", "ORGANISATION_NAME",
        "COMPANY", "COMPANY_NAME", "INSTITUTION", "I", "IO", "IC", "IA", "IF", "IG",
    }
)  # fmt: skip
_ADDRESS_LABELS = frozenset(
    {
        "LOC", "LOCATION", "GEO_LOCATION", "POSTAL_ADDRESS", "ADDRESS", "FULL_ADDRESS",
        "STREET_ADDRESS", "STREET_NAME", "STREET", "BUILDING_NUMBER", "HOUSE_NUMBER",
        "SECONDARY_ADDRESS", "CITY", "TOWN", "STATE", "REGION", "ZIP_CODE", "ZIP",
        "POSTAL_CODE", "POSTCODE", "COUNTRY", "GPE", "LOCALITY", "G", "A", "GU", "GS", "GQ",
        "GC", "GR", "AH", "AZ",
    }
)  # fmt: skip
_DATE_LABELS = frozenset(
    {"DATE", "DATE_OF_BIRTH", "BIRTH_DATE", "DOB", "BIRTHDAY", "T", "TD", "TM", "TY", "DATE_TIME"}
)


def label_to_type(raw: str) -> str | None:
    """Map a checkpoint's label to PERSON / ORG / ADDRESS / DATE, or None to drop it."""
    label = (raw or "").strip()
    for prefix in ("B-", "I-", "E-", "S-", "L-", "U-"):
        if label.startswith(prefix):
            label = label[len(prefix) :]
            break
    label = label.upper().replace("-", "_")
    if label in _PERSON_LABELS or (
        label.startswith("PERSON") and "ID" not in label and "IDENTIFIER" not in label
    ):
        return "PERSON"
    if label in _ORG_LABELS or label.startswith(("ORG", "COMPANY")):
        return "ORG"
    if label in _ADDRESS_LABELS:
        return "ADDRESS"
    if label in _DATE_LABELS:
        return "DATE"
    return None


_unmapped_seen: set[tuple[str, str]] = set()


class NerBackendError(RuntimeError):
    """A requested NER backend could not be loaded or run."""


# ---------------------------------------------------------------------------
# Model loaders (cached per process)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_bardsai():
    """Load the bardsai ONNX-quantised token-classification pipeline (CPU)."""
    from optimum.onnxruntime import ORTModelForTokenClassification
    from transformers import AutoTokenizer, pipeline

    model = ORTModelForTokenClassification.from_pretrained(
        PRIMARY_MODEL,
        file_name="model_quantized.onnx",
        subfolder="onnx",
    )
    tok = AutoTokenizer.from_pretrained(PRIMARY_MODEL)
    return pipeline(
        "token-classification",
        model=model,
        tokenizer=tok,
        aggregation_strategy="simple",
    )


@lru_cache(maxsize=1)
def _load_richielo():
    """Load the richielo small-e-czech NER pipeline (PyTorch CPU)."""
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    model = AutoModelForTokenClassification.from_pretrained(FALLBACK_MODEL)
    tok = AutoTokenizer.from_pretrained(FALLBACK_MODEL)
    return pipeline(
        "token-classification",
        model=model,
        tokenizer=tok,
        aggregation_strategy="simple",
    )


@lru_cache(maxsize=1)
def _load_gliner():
    """Load the GLiNER open-vocabulary model."""
    from gliner import GLiNER

    return GLiNER.from_pretrained(GLINER_MODEL)


def _load_tokenizer(model_id: str, kwargs: dict[str, Any], model_type: str):
    """Load a tokenizer, falling back to the raw ``tokenizer.json`` for checkpoints saved with transformers 5.

    Those checkpoints name tokenizer classes or config shapes that 4.x does not
    know; the tokenizer file itself loads. ModernBERT-style encoders take no
    ``token_type_ids``, so the fallback tokenizer only emits ids and the mask.
    """
    from transformers import AutoTokenizer

    try:
        return AutoTokenizer.from_pretrained(model_id, **kwargs)
    except (ValueError, AttributeError, TypeError) as exc:
        logger.info("ner: AutoTokenizer failed for %s (%s); loading tokenizer.json", model_id, exc)
        from huggingface_hub import hf_hub_download
        from transformers import PreTrainedTokenizerFast

        tok = PreTrainedTokenizerFast(
            tokenizer_file=hf_hub_download(model_id, "tokenizer.json", **kwargs)
        )
        if model_type in ("modernbert", "mmbert"):
            tok.model_input_names = ["input_ids", "attention_mask"]
        return tok


@lru_cache(maxsize=8)
def _load_hf_pipeline(model_id: str, revision: str | None, onnx_file: str | None = None):
    """Load any HuggingFace token-classification checkpoint as a CPU pipeline.

    ``onnx_file`` selects an ONNX graph in the repo (through optimum) for
    checkpoints that ship no PyTorch weights.
    """
    from transformers import AutoConfig, AutoModelForTokenClassification, pipeline

    kwargs = {"revision": revision} if revision else {}
    config = AutoConfig.from_pretrained(model_id, **kwargs)
    if onnx_file:
        from optimum.onnxruntime import ORTModelForTokenClassification

        model = ORTModelForTokenClassification.from_pretrained(
            model_id, file_name=onnx_file, **kwargs
        )
    else:
        model = AutoModelForTokenClassification.from_pretrained(model_id, **kwargs)
    tok = _load_tokenizer(model_id, kwargs, getattr(config, "model_type", ""))
    if tok.model_max_length is None or tok.model_max_length > 100_000:
        tok.model_max_length = getattr(config, "max_position_embeddings", 512)
    return pipeline(
        "token-classification",
        model=model,
        tokenizer=tok,
        aggregation_strategy="simple",
    )


@lru_cache(maxsize=1)
def _load_gliner2():
    """Load GLiNER 2.5 through the ``gliner2`` package."""
    from gliner2 import AutoExtractor

    return AutoExtractor.from_pretrained(GLINER2_MODEL)


# ---------------------------------------------------------------------------
# Span conversion
# ---------------------------------------------------------------------------


_ABBREVIATION_TAIL = re.compile(r"\w\.\w\.$")  # "a.s.", "s.r.o." keep their final dot


def trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Drop trailing whitespace and punctuation some taggers absorb into a span.

    A final dot stays when it closes an abbreviation such as "s.r.o." or "a.s.",
    which is part of a company name.
    """
    while start < end and text[start] in " \t\n\r":
        start += 1
    while end > start:
        ch = text[end - 1]
        if ch in " \t\n\r,;:":
            end -= 1
        elif ch == "." and not _ABBREVIATION_TAIL.search(text[start:end]):
            end -= 1
        else:
            break
    return start, end


def snap_to_word(text: str, start: int, end: int) -> tuple[int, int]:
    """Extend a span that starts or ends inside a word to the whole word.

    Subword tokenisation makes a tagger stop inside an inflected Czech surname
    ("Sedláčkov" of "Sedláčkovi", "Jan" of "Jandou"); a personal-data span never
    ends mid-word, so the boundary moves to the next non-letter.
    """
    while start > 0 and text[start - 1].isalpha() and text[start].isalpha():
        start -= 1
    while end < len(text) and text[end].isalpha() and text[end - 1].isalpha():
        end += 1
    return start, end


def _convert_entities(
    entities: list[dict[str, Any]],
    text: str,
    to_type: Callable[[str], str | None],
    source: str,
) -> list[dict[str, Any]]:
    """Convert HF pipeline entities to UC-02 span records.

    ``to_type`` maps the checkpoint's label to a canonical type or ``None`` (dropped);
    a dropped label is logged once per backend so a smoke run shows what a model
    emits that the taxonomy does not take.
    """
    spans: list[dict[str, Any]] = []
    for ent in entities:
        raw = ent.get("entity_group") or ent.get("entity") or ""
        group = raw[2:] if raw.startswith(("B-", "I-")) else raw
        pii_type = to_type(group)
        if pii_type is None:
            if (source, raw) not in _unmapped_seen:
                _unmapped_seen.add((source, raw))
                logger.info("ner[%s]: label %r not mapped, dropped", source, raw)
            continue
        start, end = trim_span(text, int(ent["start"]), int(ent["end"]))
        if end <= start:
            continue
        start, end = snap_to_word(text, start, end)
        spans.append(
            {
                "span_start": start,
                "span_end": end,
                "pii_type": pii_type,
                "surface_form": text[start:end],
                "ner_confidence": float(ent.get("score", 0.0)),
                "source": source,
            }
        )
    return spans


def _gliner_detect(text: str, threshold: float) -> list[dict[str, Any]]:
    """Run GLiNER with the canonical labels and convert to span records."""
    raw = _load_gliner().predict_entities(text, list(_GLINER_LABELS), threshold=threshold)
    spans: list[dict[str, Any]] = []
    for e in raw:
        label = e["label"]
        if label not in _GLINER_LABELS:
            continue
        start, end = trim_span(text, int(e["start"]), int(e["end"]))
        if end <= start:
            continue
        start, end = snap_to_word(text, start, end)
        spans.append(
            {
                "span_start": start,
                "span_end": end,
                "pii_type": label,
                "surface_form": text[start:end],
                "ner_confidence": float(e.get("score", 0.0)),
                "source": "ner:gliner",
            }
        )
    return spans


def _gliner2_detect(text: str, threshold: float) -> list[dict[str, Any]]:
    """Run GLiNER 2.5 with the four label strings; locate entities in the text."""
    result = _load_gliner2().extract_entities(
        text,
        list(_GLINER2_LABELS),
        threshold=threshold,
        include_confidence=True,
        include_spans=True,
    )
    entities = result.get("entities", result) if isinstance(result, dict) else {}
    spans: list[dict[str, Any]] = []
    for label, items in entities.items():
        pii_type = _GLINER2_LABELS.get(label)
        if pii_type is None:
            continue
        for item in items or []:
            if isinstance(item, dict):
                surface = str(item.get("text", ""))
                score = float(item.get("confidence", item.get("score", 1.0)))
                start = item.get("start")
                end = item.get("end")
            else:
                surface, score, start, end = str(item), 1.0, None, None
            occurrences: list[tuple[int, int]] = []
            if isinstance(start, int) and isinstance(end, int) and text[start:end] == surface:
                occurrences.append((start, end))
            else:
                at = text.find(surface)
                while surface and at != -1:
                    occurrences.append((at, at + len(surface)))
                    at = text.find(surface, at + len(surface))
            for s0, e0 in occurrences:
                s1, e1 = trim_span(text, s0, e0)
                if e1 <= s1:
                    continue
                s1, e1 = snap_to_word(text, s1, e1)
                spans.append(
                    {
                        "span_start": s1,
                        "span_end": e1,
                        "pii_type": pii_type,
                        "surface_form": text[s1:e1],
                        "ner_confidence": score,
                        "source": "ner:gliner2",
                    }
                )
    return spans


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_ner(
    text: str,
    *,
    backend: str | None = None,
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Detect PERSON / ORG / ADDRESS / DATE spans with one named backend.

    Args:
        text: Source text.
        backend: One of ``NER_BACKENDS``; ``None`` means ``DEFAULT_NER_BACKEND``.
        threshold: Minimum confidence; spans below are dropped.

    Returns:
        Span records ``{span_start, span_end, pii_type, surface_form, ner_confidence,
        source}`` with ``pii_type`` in PERSON / ORG / ADDRESS / DATE.

    Raises:
        NerBackendError: unknown backend, or the backend failed to load or run.
        There is no fallback to another model on purpose.
    """
    if not text.strip():
        return []
    name = backend or DEFAULT_NER_BACKEND
    if name not in NER_BACKENDS:
        raise NerBackendError(f"unknown NER backend {name!r}; choices: {NER_BACKENDS}")
    try:
        if name == "presidio":
            from ucs.uc02_pseudonymization.code.ner_presidio import detect_presidio

            spans = detect_presidio(text, threshold=threshold)
            for span in spans:
                span["source"] = "ner:presidio"
            return spans
        if name == "gliner":
            return _gliner_detect(text, threshold)
        if name == "gliner2":
            spans = _gliner2_detect(text, threshold)
        elif name in CANDIDATE_MODELS:
            spec = CANDIDATE_MODELS[name]
            entities = _load_hf_pipeline(
                str(spec["model"]), spec["revision"], spec.get("onnx_file")
            )(text)
            spans = _convert_entities(entities, text, label_to_type, f"ner:{name}")
        elif name == "richielo":
            entities = _load_richielo()(text)
            spans = _convert_entities(entities, text, _RICHIELO_LABEL_MAP.get, "ner:richielo")
        else:
            entities = _load_bardsai()(text)
            spans = _convert_entities(entities, text, _BARDSAI_LABEL_MAP.get, "ner:bardsai")
    except NerBackendError:
        raise
    except Exception as exc:
        raise NerBackendError(f"NER backend {name!r} failed: {exc}") from exc
    return [span for span in spans if span["ner_confidence"] >= threshold]


__all__ = [
    "CANDIDATE_MODELS",
    "DEFAULT_NER_BACKEND",
    "LICENCES",
    "MODEL_IDS",
    "NER_BACKENDS",
    "label_to_type",
    "NerBackendError",
    "detect_ner",
    "trim_span",
    "snap_to_word",
    "PRIMARY_MODEL",
    "FALLBACK_MODEL",
    "GLINER_MODEL",
]
