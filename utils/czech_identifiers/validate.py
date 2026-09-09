"""Checksum and format rules for Czech identifiers.

The half UC-02 uses at run time: ``pseudonymizer.py`` runs every regex match
from :mod:`utils.czech_identifiers.patterns` through these before it will tag a
span, so an eight-digit invoice number is not reported as an IČO. That gate is
what makes the detector's precision defensible rather than regex-shaped.

Pure functions: no I/O, no randomness, no network.
"""

from __future__ import annotations

import calendar

_ICO_WEIGHTS = (8, 7, 6, 5, 4, 3, 2)


# ---------------------------------------------------------------------------
# Shared calendar rule
# ---------------------------------------------------------------------------


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given calendar month.

    Package-internal: the generator side imports it so a generated rodné číslo
    and a validated one agree on what a real date is.
    """
    return calendar.monthrange(year, month)[1]


# Month field of a rodné číslo -> real month. Men use the plain month; women's
# is raised by 50. Since 2004 (zákon č. 53/2004 Sb.) both may be raised by a
# further 20 when the four-digit sequence for that day is exhausted, giving men
# 21-32 and women 71-82.
_RC_MONTH_OFFSETS = (0, 20, 50, 70)


# ---------------------------------------------------------------------------
# IČO
# ---------------------------------------------------------------------------


def ico_check_digit(seven: str) -> int:
    """Return the MOD-11 check digit for the first seven digits of an IČO.

    Algorithm (Czech Statistical Office):
        s = sum(digit_i * weight_i)  for weights (8,7,6,5,4,3,2)
        c = (11 - (s % 11)) % 10
    """
    s = sum(int(d) * w for d, w in zip(seven, _ICO_WEIGHTS))
    return (11 - (s % 11)) % 10


def is_valid_ico(value: str) -> bool:
    """Validate an 8-digit Czech IČO by its MOD-11 check digit."""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) != 8:
        return False
    return int(digits[-1]) == ico_check_digit(digits[:7])


# ---------------------------------------------------------------------------
# IBAN
# ---------------------------------------------------------------------------


def is_valid_iban_cz(value: str) -> bool:
    """Validate a Czech IBAN (CZ + 2 check digits + 20 BBAN digits) via ISO 7064 MOD-97-10."""
    raw = "".join(value.split()).upper()
    if not raw.startswith("CZ") or len(raw) != 24 or not raw[2:].isdigit():
        return False
    rearranged = raw[4:] + raw[:4]
    try:
        num_str = "".join(str(int(c, 36)) for c in rearranged)
    except ValueError:
        return False
    return int(num_str) % 97 == 1


# ---------------------------------------------------------------------------
# Rodné číslo
# ---------------------------------------------------------------------------


def is_valid_rc(value: str) -> bool:
    """Validate a Czech rodné číslo (RC).

    Format: YYMMDD/XXXX (10 digits with slash) or YYMMDD/XXX (9 digits, pre-1954 short form).
    Modern (post-1953) RCs are mod-11 valid. Pre-1954 short-form RCs (9 digits) are accepted
    by format only — they predate the check digit requirement.
    """
    digits = value.replace("/", "")
    if not digits.isdigit() or len(digits) not in (9, 10):
        return False
    yy = int(digits[0:2])
    mm = int(digits[2:4])
    dd = int(digits[4:6])

    real_month = next((mm - off for off in _RC_MONTH_OFFSETS if 1 <= mm - off <= 12), None)
    if real_month is None:
        return False

    if len(digits) == 9:
        # Pre-1954 short form. The two-digit year cannot be resolved to a
        # century from the number alone (the form covers births up to 1953, so
        # a high yy is an 18xx birth), and the century only ever matters for
        # 29 February. Rather than guess, accept a 29th and check the rest.
        if not (1 <= dd <= 31):
            return False
        if real_month != 2:
            return dd <= _days_in_month(2001, real_month)  # any non-leap year
        return dd <= 29
    return _is_valid_rc_checksum(digits, yy, dd, real_month)


def _is_valid_rc_checksum(digits: str, yy: int, dd: int, real_month: int) -> bool:
    """Day-of-month and mod-11 rules for the 10-digit (post-1953) form."""
    # A 10-digit RC was issued from 1954, so yy >= 54 is a 19xx birth.
    year = (1900 if yy >= 54 else 2000) + yy
    if not (1 <= dd <= _days_in_month(year, real_month)):
        return False

    remainder = int(digits[:9]) % 11
    if remainder == 10:
        # Historical exception: no digit 0-9 could satisfy a remainder of 10, so
        # the check digit was written as 0 and the whole number is NOT divisible
        # by 11. About a thousand such numbers exist; issuance stopped in 1985.
        return int(digits[9]) == 0
    return int(digits[9]) == remainder


__all__ = [
    "ico_check_digit",
    "is_valid_ico",
    "is_valid_iban_cz",
    "is_valid_rc",
]
