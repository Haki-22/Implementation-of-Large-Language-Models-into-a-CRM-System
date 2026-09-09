"""Surface-form recognizers for Czech identifiers.

Shape only: these say "this looks like an IČO", never "this is a valid IČO".
A consumer that needs the second answer runs the match through
:mod:`utils.czech_identifiers.validate` — that split is what lets UC-02 detect
with a cheap regex and then reject the false positives by checksum.

One catalogue so the rule-based pseudonymiser and the Presidio backend cannot
drift apart: both read ``REGEX``.
"""

from __future__ import annotations

import re

REGEX: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # +420 prefix optional; groups may be separated by spaces or dots.
    "PHONE": re.compile(r"(?:\+420[\s.]*)?(?:\d{3}[\s.]*){2}\d{3}\b"),
    # Bare 9-digit Czech mobile (no +420), first digit constrained to the
    # mobile + landline range — used by Presidio's loose recognizer.
    "PHONE_BARE9": re.compile(r"\b[2-79]\d{2}\s?\d{3}\s?\d{3}\b"),
    "RC": re.compile(r"\b\d{6}/\d{3,4}\b"),
    # The country prefix in any case: typed input is not always upper-case, and the
    # validators upper-case the candidate anyway (casing table of 2026-09-07).
    "DIC": re.compile(r"\bCZ\d{8}\b", re.IGNORECASE),
    "ICO": re.compile(r"\b\d{8}\b"),
    "IBAN": re.compile(r"\bCZ\d{2}(?:\s?\d{4}){5}\b", re.IGNORECASE),
    "BBAN": re.compile(r"\b(?:\d{1,6}-)?\d{2,10}/\d{4}\b"),
    "PSC": re.compile(r"\b\d{3}\s?\d{2}\b"),
}

__all__ = ["REGEX"]
