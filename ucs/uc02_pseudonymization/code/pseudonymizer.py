"""UC-02 reversible pseudonymisation: detection, merge, masking, restore, scoring.

Detection has two layers. The rule layer (``detect_rule_based``) finds format-bearing
Czech identifiers with the shared regexes and rejects every candidate that fails its
checksum. The NER layer (``ner.detect_ner``) finds PERSON / ORG / ADDRESS / DATE. The two
streams meet in ``merge_spans``, the single place where overlaps are decided.

Labels are the gold labels: EMAIL, PHONE, ICO, DIC, RC, IBAN_CZ, BBAN, PSC from the
rules; PERSON, ORG, ADDRESS, DATE from the NER. A detector that emits a label the
answer key does not know cannot be scored, so no alias table exists anywhere else.
"""

from __future__ import annotations

import json
import logging
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from utils.czech_identifiers.patterns import REGEX as _PII_REGEX
from utils.czech_identifiers.validate import (
    is_valid_iban_cz,
    is_valid_ico,
    is_valid_rc,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Placeholder shape. Used to reserve tokens that already sit in the input so a
# fresh token never collides with a tag-shaped substring the user supplied.
TAG_PATTERN = re.compile(r"<([A-Z][A-Z_]*)_(\d+)([a-z]*)>")

# The one rule label that carries no checksum and therefore yields to an NER
# span that contains it (a postal code inside an address). Every other rule
# label wins on overlap.
YIELDING_RULE_LABELS: frozenset[str] = frozenset({"PSC"})

# What may sit between two NER fragments of the same type for them to be one
# span. Whitespace for every type; an address also spans commas ("Adélčina 72"
# + ", " + "459 77 Poběžovice") and a Czech date spans dots ("23. 3. 1969"). Two
# person names separated by a comma stay two spans.
_FRAGMENT_GAP = re.compile(r"\s*")
_FRAGMENT_GAP_BY_TYPE: dict[str, re.Pattern[str]] = {
    "ADDRESS": re.compile(r"[\s,]*"),
    "DATE": re.compile(r"[\s.]*"),
}

_EMAIL_RE = _PII_REGEX["EMAIL"]
_PHONE_RE = _PII_REGEX["PHONE"]
_RC_RE = _PII_REGEX["RC"]
_DIC_RE = _PII_REGEX["DIC"]
_ICO_RE = _PII_REGEX["ICO"]
_IBAN_RE = _PII_REGEX["IBAN"]
_BANK_ACCOUNT_RE = _PII_REGEX["BBAN"]
_PSC_RE = _PII_REGEX["PSC"]


# ---------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------


def _span_record(start: int, end: int, pii_type: str, text: str, source: str) -> dict[str, Any]:
    """Build one detected span record.

    ``source`` names the layer that produced the span (``"rule"`` or ``"ner:<backend>"``)
    so a masked text can say what masked it.
    """
    return {
        "span_start": start,
        "span_end": end,
        "pii_type": pii_type,
        "surface_form": text[start:end],
        "source": source,
    }


def _scan_existing_tags(text: str) -> set[tuple[str, int]]:
    """Return ``{(pii_type, number)}`` of any ``<TYPE_N>`` tags already in text."""
    return {(m.group(1), int(m.group(2))) for m in TAG_PATTERN.finditer(text)}


def _positions(span: dict[str, Any]) -> set[int]:
    """Return the character positions a span covers."""
    return set(range(int(span["span_start"]), int(span["span_end"])))


# ---------------------------------------------------------------------------
# Detection: the rule layer
# ---------------------------------------------------------------------------


def detect_rule_based(text: str) -> list[dict[str, Any]]:
    """Detect format-bearing Czech identifiers with deterministic recognisers.

    Every IČO, rodné číslo and IBAN candidate runs through its checksum before it
    becomes a span; e-mail, phone, DIČ, postal code and domestic bank account are
    shape-only. PERSON, ORG, ADDRESS and DATE are intentionally not detected here:
    they need the NER layer.
    """
    spans: list[dict[str, Any]] = []
    for pii_type, pattern in (
        ("EMAIL", _EMAIL_RE),
        ("PHONE", _PHONE_RE),
        ("DIC", _DIC_RE),
        ("PSC", _PSC_RE),
    ):
        for match in pattern.finditer(text):
            spans.append(_span_record(match.start(), match.end(), pii_type, text, "rule"))
    for match in _ICO_RE.finditer(text):
        if is_valid_ico(match.group(0)):
            spans.append(_span_record(match.start(), match.end(), "ICO", text, "rule"))
    for match in _RC_RE.finditer(text):
        if is_valid_rc(match.group(0)):
            spans.append(_span_record(match.start(), match.end(), "RC", text, "rule"))
    for match in _IBAN_RE.finditer(text):
        if is_valid_iban_cz(match.group(0)):
            spans.append(_span_record(match.start(), match.end(), "IBAN_CZ", text, "rule"))
    for match in _BANK_ACCOUNT_RE.finditer(text):
        spans.append(_span_record(match.start(), match.end(), "BBAN", text, "rule"))
    return _dedupe_rule_spans(spans)


def _dedupe_rule_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve rule-vs-rule overlaps: the longer span wins, then the earlier one."""
    ordered = sorted(spans, key=lambda s: (-(s["span_end"] - s["span_start"]), s["span_start"]))
    kept: list[dict[str, Any]] = []
    occupied: set[int] = set()
    for span in ordered:
        positions = _positions(span)
        if positions & occupied:
            continue
        kept.append(span)
        occupied.update(positions)
    return sorted(kept, key=lambda s: s["span_start"])


# ---------------------------------------------------------------------------
# Merge: rules + NER
# ---------------------------------------------------------------------------


def join_adjacent_fragments(spans: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    """Join same-type spans separated only by whitespace or commas into one span.

    Token-level NER returns an address as pieces ("Adélčina 72" and "459 77
    Poběžovice", or single words) more often than as one span. The unit the answer
    key marks and the unit one token replaces is the whole address, so the pieces
    are joined before any overlap decision. The joined span keeps the lowest
    confidence of its parts.
    """
    out: list[dict[str, Any]] = []
    for span in sorted(spans, key=lambda s: int(s["span_start"])):
        if out and out[-1]["pii_type"] == span["pii_type"]:
            gap = text[int(out[-1]["span_end"]) : int(span["span_start"])]
            if _FRAGMENT_GAP_BY_TYPE.get(span["pii_type"], _FRAGMENT_GAP).fullmatch(gap):
                previous = out[-1]
                start = int(previous["span_start"])
                end = int(span["span_end"])
                joined = {**previous, "span_end": end, "surface_form": text[start:end]}
                if "ner_confidence" in previous or "ner_confidence" in span:
                    joined["ner_confidence"] = min(
                        float(previous.get("ner_confidence", 1.0)),
                        float(span.get("ner_confidence", 1.0)),
                    )
                out[-1] = joined
                continue
        out.append(dict(span))
    return out


def merge_spans(
    rule_spans: list[dict[str, Any]],
    ner_spans: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    """Combine the rule layer and the NER layer into one non-overlapping span list.

    Order of precedence:

    1. Rule spans with a checksum or a hard shape (everything but PSC) are placed first;
       an NER span that overlaps them is dropped (a name-shaped e-mail prefix, a
       phone tagged as a location).
    2. NER spans, fragments joined, most confident first.
    3. PSC spans last, only where no span sits yet: a postal code inside a detected
       address yields to the address; a postal code standing alone is still masked.

    Every returned span carries its ``source``.
    """
    occupied: set[int] = set()
    kept: list[dict[str, Any]] = []

    def _place(span: dict[str, Any]) -> None:
        """Keep `span` if it does not overlap anything already placed, else drop it."""
        positions = _positions(span)
        if positions & occupied:
            return
        kept.append(span)
        occupied.update(positions)

    for span in rule_spans:
        if span["pii_type"] not in YIELDING_RULE_LABELS:
            _place(span)
    for span in sorted(
        join_adjacent_fragments(ner_spans, text),
        key=lambda s: -float(s.get("ner_confidence", 0.0)),
    ):
        _place(span)
    for span in rule_spans:
        if span["pii_type"] in YIELDING_RULE_LABELS:
            _place(span)
    return sorted(kept, key=lambda s: s["span_start"])


# ---------------------------------------------------------------------------
# Masking and restore
# ---------------------------------------------------------------------------


UNIFY_MODES: tuple[str, ...] = ("none", "exact", "entity")
NUMBERING_MODES: tuple[str, ...] = ("reading", "random")
RANDOM_ID_RANGE = (1, 9999)

# Czech surname endings, longest first. Each maps to the paradigm class it belongs
# to: "f" for the feminine -ová paradigm, "m" for masculine nouns, "adj" for
# adjectival surnames (Černý / Černá share one stem, so they get one class). The
# stem is what is left after the ending. A surface form with no listed ending is
# its own stem in class "m". This is a heuristic for a measurement (D-UC02-4);
# false merges and missed unifications are counted against the gold entity ids.
_SURNAME_ENDINGS: tuple[tuple[str, str], ...] = (
    ("ovou", "f"),
    ("ové", "f"),
    ("ová", "f"),
    ("ého", "adj"),
    ("ému", "adj"),
    ("ým", "adj"),
    ("ém", "adj"),
    ("ovi", "m"),
    ("em", "m"),
    ("ou", "m"),
    ("ý", "adj"),
    ("á", "adj"),
    ("é", "adj"),
    ("a", "m"),
    ("e", "m"),
    ("u", "m"),
    ("y", "m"),
    ("i", "m"),
)
_MIN_STEM = 3


def _drop_fleeting_e(stem: str) -> str:
    """Return the stem without the fleeting -e- of -ek / -el nouns (Hájek → hájk, Pavel → pavl)."""
    if len(stem) > 3 and stem.endswith(("ek", "el")) and stem[-3] not in "aeiouáéíóúůy":
        return stem[:-2] + stem[-1]
    return stem


def _surname_key(word: str) -> tuple[str, str]:
    """Return ``(stem, paradigm class)`` of one Czech surname surface form."""
    lowered = word.lower()
    for ending, cls in _SURNAME_ENDINGS:
        if lowered.endswith(ending) and len(lowered) - len(ending) >= _MIN_STEM:
            return _drop_fleeting_e(lowered[: -len(ending)]), cls
    return _drop_fleeting_e(lowered), "m"


def surname_stem(word: str) -> str:
    """Return the stem of one Czech surname form (the part all its cases share)."""
    return _surname_key(word)[0]


def entity_key(pii_type: str, surface_form: str) -> tuple[str, ...]:
    """Return the key two spans share when they name the same entity.

    PERSON spans are keyed by the stem and paradigm class of their last word, so
    "Jan Novák", "Nováka" and "panu Novákovi" (the span being "Novákovi") share a
    key while "Nováková" does not. Every other type is keyed by its exact surface
    form, whitespace collapsed.
    """
    collapsed = " ".join(surface_form.split())
    if pii_type == "PERSON" and collapsed:
        stem, cls = _surname_key(collapsed.split()[-1])
        return (pii_type, stem, cls)
    return (pii_type, collapsed)


def _form_suffix(index: int) -> str:
    """Return the letter suffix of the ``index``-th form of an entity: "", "b", …, "z", "aa", …"""
    if index == 0:
        return ""
    letters = ""
    n = index
    while True:
        letters = chr(ord("a") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            return letters


class _Numbering:
    """Allocate token numbers per message in reading order or at random."""

    def __init__(self, mode: str, text: str, rng: random.Random | None) -> None:
        """Set up numbering for one message; reserve any ``<TYPE_N>`` tags already in `text`.

        Args:
            mode: One of `NUMBERING_MODES` (``"reading"`` or ``"random"``).
            text: The source text, scanned for pre-existing tag-shaped
                substrings so a fresh token never collides with one.
            rng: Seeded ``random.Random`` for the ``"random"`` mode, or
                ``None`` to use a fresh, unseeded one.
        """
        if mode not in NUMBERING_MODES:
            raise ValueError(f"numbering must be one of {NUMBERING_MODES}, got {mode!r}")
        self.mode = mode
        self.rng = rng or random.Random()
        self.used_by_type: dict[str, set[int]] = defaultdict(set)
        self.used_any: set[int] = set()
        self.next_by_type: dict[str, int] = {}
        for pii_type, n in _scan_existing_tags(text):
            self.used_by_type[pii_type].add(n)
            self.used_any.add(n)

    def take(self, pii_type: str) -> int:
        """Return a fresh number for ``pii_type``."""
        if self.mode == "reading":
            n = self.next_by_type.get(pii_type, 1)
            while n in self.used_by_type[pii_type]:
                n += 1
            self.used_by_type[pii_type].add(n)
            self.next_by_type[pii_type] = n + 1
            return n
        for _ in range(100):
            n = self.rng.randint(*RANDOM_ID_RANGE)
            if n not in self.used_any:
                self.used_any.add(n)
                self.used_by_type[pii_type].add(n)
                return n
        raise RuntimeError("could not allocate a fresh random token number")


def pseudonymize_text(
    text: str,
    spans: list[dict[str, Any]],
    *,
    unify: str = "none",
    numbering: str = "reading",
    rng: random.Random | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Replace detected spans with per-message tokens and return the mapping.

    ``unify`` decides when two spans share a token:
        ``"none"``    every span gets its own token (the baseline);
        ``"exact"``   spans with the same type and surface form share one token;
        ``"entity"``  spans naming the same entity share one number, and each
                      distinct surface form of it gets a letter suffix
                      (``<PERSON_1>`` for "Jan Novák", ``<PERSON_1b>`` for
                      "Novákovi"), so every token still restores to exactly the
                      text it replaced and no ordering of mentions is assumed.

    ``numbering`` is ``"reading"`` (first PERSON in the text is ``<PERSON_1>``) or
    ``"random"`` (numbers drawn from ``RANDOM_ID_RANGE`` with ``rng``, unique per
    message, so a number leaks no order). Tokens already present in ``text`` are
    reserved first so a new token never collides with a tag-shaped substring the
    user supplied. Replacement walks the string from the end so earlier offsets
    stay valid. One mapping record per span; records sharing a token carry the
    same ``entity`` number.
    """
    if unify not in UNIFY_MODES:
        raise ValueError(f"unify must be one of {UNIFY_MODES}, got {unify!r}")
    numbers = _Numbering(numbering, text, rng)
    spans_forward = sorted(spans, key=lambda item: int(item["span_start"]))

    token_by_key: dict[tuple[str, ...], str] = {}
    number_by_entity: dict[tuple[str, ...], int] = {}
    forms_by_entity: dict[tuple[str, ...], list[str]] = defaultdict(list)
    span_token: list[tuple[dict[str, Any], str, int]] = []

    for span in spans_forward:
        pii_type = str(span["pii_type"])
        surface = text[int(span["span_start"]) : int(span["span_end"])]
        exact = (pii_type, surface)
        if unify == "none":
            n = numbers.take(pii_type)
            token = f"<{pii_type}_{n}>"
        elif unify == "exact":
            if exact not in token_by_key:
                n = numbers.take(pii_type)
                token_by_key[exact] = f"<{pii_type}_{n}>"
                number_by_entity[exact] = n
            token = token_by_key[exact]
            n = number_by_entity[exact]
        else:
            entity = entity_key(pii_type, surface)
            if entity not in number_by_entity:
                number_by_entity[entity] = numbers.take(pii_type)
            n = number_by_entity[entity]
            forms = forms_by_entity[entity]
            if surface not in forms:
                forms.append(surface)
            suffix = _form_suffix(forms.index(surface))
            token = f"<{pii_type}_{n}{suffix}>"
        span_token.append((span, token, n))

    mapping: list[dict[str, Any]] = []
    pseudonymized = text
    for span, token, n in sorted(span_token, key=lambda st: -int(st[0]["span_start"])):
        start = int(span["span_start"])
        end = int(span["span_end"])
        pseudonymized = pseudonymized[:start] + token + pseudonymized[end:]
        mapping.append(
            {
                "token": token,
                "pii_type": str(span["pii_type"]),
                "surface_form": text[start:end],
                "span_start": start,
                "span_end": end,
                "entity": n,
                "source": str(span.get("source", "unknown")),
            }
        )
    mapping.sort(key=lambda item: item["span_start"])
    return pseudonymized, mapping


def unification_summary(mapping: list[dict[str, Any]]) -> dict[str, int]:
    """Count spans, distinct tokens and distinct entities in one mapping.

    The unification rate of a mode is ``1 - entities / spans`` over a corpus: the
    share of spans that were recognised as a repeat of an earlier entity (in the
    entity mode a repeat may carry its own suffixed token, so tokens stay per
    form while entities merge).
    """
    return {
        "spans": len(mapping),
        "tokens": len({m["token"] for m in mapping}),
        "entities": len({(m["pii_type"], m["entity"]) for m in mapping}),
    }


def restore_text(pseudonymized: str, mapping: list[dict[str, Any]]) -> str:
    """Restore original values from a pseudonymised message and its mapping."""
    restored = pseudonymized
    for item in sorted(mapping, key=lambda value: len(value["token"]), reverse=True):
        restored = restored.replace(item["token"], item["surface_form"])
    return restored


def pseudonymize(
    text: str,
    *,
    use_ner: bool = True,
    ner_threshold: float = 0.5,
    ner_backend: str | None = None,
    unify: str = "none",
    numbering: str = "reading",
    rng: random.Random | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Detect personal data (rules, optionally plus NER) and mask it.

    Parameters
    ----------
    text:
        Source Czech text.
    use_ner:
        Run the NER layer for PERSON / ORG / ADDRESS / DATE on top of the rules.
    ner_threshold:
        Minimum NER confidence for a span to count.
    ner_backend:
        NER backend name; ``None`` means the package default (``ner.DEFAULT_NER_BACKEND``).
    unify, numbering, rng:
        Token policies, see :func:`pseudonymize_text`.

    Returns
    -------
    (masked_text, mapping)
        ``masked_text`` holds the ``<TYPE_N>`` tokens; ``mapping`` is the list of
        records produced by :func:`pseudonymize_text`, each with its ``source``.

    Raises
    ------
    RuntimeError
        When the NER layer was requested and could not run. Masking silently with
        the rules alone would let names and addresses through, so the caller
        decides what to do.
    """
    rule_spans = detect_rule_based(text)
    if not use_ner:
        return pseudonymize_text(text, rule_spans, unify=unify, numbering=numbering, rng=rng)

    from ucs.uc02_pseudonymization.code.ner import detect_ner

    ner_spans = [
        span
        for span in detect_ner(text, backend=ner_backend, threshold=ner_threshold)
        if float(span.get("ner_confidence", 0.0)) >= ner_threshold
    ]
    return pseudonymize_text(
        text, merge_spans(rule_spans, ner_spans, text), unify=unify, numbering=numbering, rng=rng
    )


def depseudonymize(masked_or_modified: str, mapping: list[dict[str, Any]]) -> str:
    """Restore original values from a masked text that a model may have rewritten.

    The ``<TYPE_N>`` tokens must still be present; the text around them may differ.
    """
    return restore_text(masked_or_modified, mapping)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _span_key(span: dict[str, Any]) -> tuple[int, int, str]:
    """Return the exact-match key of one span."""
    return (int(span["span_start"]), int(span["span_end"]), str(span["pii_type"]))


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> int:
    """Return the number of characters two spans share."""
    return max(
        0,
        min(int(a["span_end"]), int(b["span_end"]))
        - max(int(a["span_start"]), int(b["span_start"])),
    )


# Prediction types that count as a partial hit on a gold span of another type: a
# postal code found inside an address hides part of the address. The gold
# convention keeps the postal code inside the ADDRESS span.
_PARTIAL_EQUIVALENT: frozenset[tuple[str, str]] = frozenset({("ADDRESS", "PSC")})


def _partially_compatible(gold_type: str, pred_type: str) -> bool:
    """Return whether a prediction of ``pred_type`` may partially match ``gold_type``."""
    return gold_type == pred_type or (gold_type, pred_type) in _PARTIAL_EQUIVALENT


def _match_message(
    gold: list[dict[str, Any]],
    pred: list[dict[str, Any]],
) -> tuple[Counter[str], Counter[str]]:
    """Return strict and partial (tp, fp, fn) counters for one message.

    Strict: a prediction is a hit only with the exact span and type of a gold span.
    Partial: a prediction that overlaps an unmatched gold span of the same type is a
    hit as well (a half-found address counts once, never twice). Each gold span and
    each prediction is matched at most once; the greedy pass takes the largest
    overlap first.
    """
    strict = Counter()
    partial = Counter()
    gold_keys = {_span_key(g) for g in gold}
    pred_keys = {_span_key(p) for p in pred}
    strict["tp"] = len(gold_keys & pred_keys)
    strict["fp"] = len(pred_keys - gold_keys)
    strict["fn"] = len(gold_keys - pred_keys)

    unmatched_gold = [g for g in gold if _span_key(g) not in pred_keys]
    unmatched_pred = [p for p in pred if _span_key(p) not in gold_keys]
    pairs = sorted(
        (
            (_overlap(g, p), gi, pi)
            for gi, g in enumerate(unmatched_gold)
            for pi, p in enumerate(unmatched_pred)
            if _partially_compatible(g["pii_type"], p["pii_type"]) and _overlap(g, p) > 0
        ),
        key=lambda t: -t[0],
    )
    used_gold: set[int] = set()
    used_pred: set[int] = set()
    overlap_hits = 0
    for _, gi, pi in pairs:
        if gi in used_gold or pi in used_pred:
            continue
        used_gold.add(gi)
        used_pred.add(pi)
        overlap_hits += 1
    partial["tp"] = strict["tp"] + overlap_hits
    partial["fp"] = strict["fp"] - overlap_hits
    partial["fn"] = strict["fn"] - overlap_hits
    return strict, partial


def _counts_to_metrics(counts: Counter[str]) -> dict[str, float | int]:
    """Convert (tp, fp, fn) counts to precision, recall and F1."""
    tp = counts["tp"]
    fp = counts["fp"]
    fn = counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def score_detection(
    gold_by_message: dict[str, list[dict[str, Any]]],
    pred_by_message: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Score predictions against gold spans, overall and per type, strict and partial.

    Returns ``{"overall", "by_type", "counts"}`` for the strict match (exact span and
    type) and the same three under ``"partial"`` for the overlap match. Messages that
    have predictions but no gold still contribute false positives.
    """
    message_ids = set(gold_by_message) | set(pred_by_message)
    labels = sorted(
        {
            str(span["pii_type"])
            for message_id in message_ids
            for span in gold_by_message.get(message_id, []) + pred_by_message.get(message_id, [])
        }
    )
    strict_all: Counter[str] = Counter()
    partial_all: Counter[str] = Counter()
    strict_by_type: dict[str, Counter[str]] = {label: Counter() for label in labels}
    partial_by_type: dict[str, Counter[str]] = {label: Counter() for label in labels}

    for message_id in message_ids:
        gold = gold_by_message.get(message_id, [])
        pred = pred_by_message.get(message_id, [])
        strict, partial = _match_message(gold, pred)
        strict_all.update(strict)
        partial_all.update(partial)
        for label in labels:
            s, p = _match_message(
                [g for g in gold if g["pii_type"] == label],
                [q for q in pred if q["pii_type"] == label],
            )
            strict_by_type[label].update(s)
            partial_by_type[label].update(p)

    return {
        "overall": _counts_to_metrics(strict_all),
        "by_type": {label: _counts_to_metrics(strict_by_type[label]) for label in labels},
        "counts": dict(strict_all),
        "partial": {
            "overall": _counts_to_metrics(partial_all),
            "by_type": {label: _counts_to_metrics(partial_by_type[label]) for label in labels},
            "counts": dict(partial_all),
        },
    }


def load_gold(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load a gold JSONL sidecar grouped by ``message_id``."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            grouped[row["message_id"]].append(row)
    return dict(grouped)
