"""UC-02 Presidio backend — industry baseline for the UC-02 A/B comparison.

Microsoft Presidio is the standard EU/EN industry framework for PII detection
(Salesforce Trust Layer is built on similar primitives). This module wires its
``AnalyzerEngine`` with Czech-specific ``PatternRecognizer``s (IČO, DIČ, RC,
bare-9-digit phone) so we can include "Presidio + CZ recognizers" as a fourth
NER backend option alongside ``gliner``, ``bardsai``, ``richielo``.

Origin: originally lived in ``ucs/uc03_mcp_privacy/analyzer.py`` (UC-03 overreach,
moved here 2026-05-31 during cleanup). The 2-backend "uc02 vs presidio" composite
in the original is dropped — UC-02 already does rule + NER fusion natively.

Limitations (document in the UC-02 evaluation report):
- Presidio's default PERSON recognizer uses an English spaCy model. Czech names
  are systematically missed. For PERSON detection on Czech text the gliner or
  bardsai backends remain superior.
- Format-PII recognizers (IČO/DIČ/RC) overlap with UC-02 rule_based + checksum
  detectors. Presidio's are pattern-only (no mod-11 checksum). Use UC-02 native
  rule_based unless A/B comparison is explicitly the goal.

Caveat for production: Presidio adds ~80 MB Python deps (spaCy + en_core_web_lg
not strictly required; default uses smaller models). License: MIT (Microsoft) +
spaCy MIT — commercial-OK.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from utils.czech_identifiers.patterns import REGEX as _PII_REGEX

logger = logging.getLogger(__name__)

# Presidio entity_type → our UC-02 canonical pii_type.
_PRESIDIO_TYPE_MAP: dict[str, str] = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "IBAN_CODE": "IBAN_CZ",
    "CREDIT_CARD": "CREDIT_CARD",
    "DATE_TIME": "DATE",
    "LOCATION": "ADDRESS",
    # Czech-custom recognizers (added below) emit these entity_types directly.
    "ICO": "ICO",
    "DIC": "DIC",
    "RC": "RC",
}


@lru_cache(maxsize=1)
def _build_presidio_analyzer():
    """Lazy-init Presidio AnalyzerEngine with Czech pattern recognizers added."""
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

    engine = AnalyzerEngine()

    # Czech IČO — 8 digits, no checksum here (UC-02 rule_based does mod-11).
    # Shape pattern shared with utils.czech_identifiers.patterns.REGEX["ICO"].
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="ICO",
            name="CzechIcoRecognizer",
            patterns=[Pattern(name="ico_8_digits", regex=_PII_REGEX["ICO"].pattern, score=0.4)],
            context=["IČO", "ico", "ič", "identifikační"],
        )
    )

    # Czech DIČ — Presidio recogniser is intentionally looser than the
    # canonical ``czech_identifiers.patterns.REGEX["DIC"]`` (allows optional space + 8-10
    # digits) so spaCy's context scoring can compensate for noisy inputs.
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="DIC",
            name="CzechDicRecognizer",
            patterns=[Pattern(name="dic_cz_prefix", regex=r"\bCZ\s?\d{8,10}\b", score=0.9)],
            context=["DIČ", "dič", "daňové"],
        )
    )

    # Czech rodné číslo — Presidio recogniser uses optional slash so it can
    # catch the slashless variant; canonical ``czech_identifiers.patterns.REGEX["RC"]`` requires
    # the slash and is reserved for the strict rule-based pseudonymiser.
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="RC",
            name="CzechRodneCisloRecognizer",
            patterns=[Pattern(name="rc", regex=r"\b\d{6}/?\d{3,4}\b", score=0.7)],
            context=["rodné", "RC"],
        )
    )

    # Czech bare 9-digit phone (Presidio's built-in handles +420 via libphonenumber).
    # Shared with ``czech_identifiers.patterns.REGEX["PHONE_BARE9"]``.
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            name="CzechBarePhoneRecognizer",
            patterns=[
                Pattern(
                    name="cz_bare_9",
                    regex=_PII_REGEX["PHONE_BARE9"].pattern,
                    score=0.55,
                )
            ],
            context=["tel", "telefon", "mobil", "číslo"],
        )
    )
    return engine


def detect_presidio(text: str, *, threshold: float = 0.5) -> list[dict[str, Any]]:
    """Run Presidio + Czech recognizers, return UC-02-shape spans.

    Output: list of ``{span_start, span_end, pii_type, surface_form, ner_confidence}``
    matching the shape ``pseudonymizer.merge_spans`` expects.
    """
    if not text.strip():
        return []
    engine = _build_presidio_analyzer()
    results = engine.analyze(text=text, language="en")
    out: list[dict[str, Any]] = []
    for r in results:
        if r.score < threshold:
            continue
        canonical = _PRESIDIO_TYPE_MAP.get(r.entity_type, "_unknown")
        if canonical == "_unknown":
            continue
        start, end = int(r.start), int(r.end)
        out.append(
            {
                "span_start": start,
                "span_end": end,
                "pii_type": canonical,
                "surface_form": text[start:end],
                "ner_confidence": float(r.score),
            }
        )
    return out


__all__ = ["detect_presidio"]
