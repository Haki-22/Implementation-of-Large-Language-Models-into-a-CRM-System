"""Czech identifier formats: how to build one, how to check one, how to spot one.

Three parts, because three different callers need different halves:

``patterns``
    ``REGEX`` — surface-form recognizers. Shape only. Read by UC-02's rule-based
    pseudonymiser and its Presidio backend, so both detect the same shapes.
``validate``
    Checksum and calendar rules (``ico_check_digit``, ``is_valid_ico``,
    ``is_valid_iban_cz``, ``is_valid_rc``). UC-02 runs every regex match through
    these before tagging a span, so an eight-digit invoice number is not
    reported as an IČO.
``generate``
    Seeded synthetic values (``generate_ico`` … ``generate_psc``). Used by the
    substrate generators to give contacts and companies identifiers, and by
    UC-02's corpus builder to plant identifiers it will then try to detect.

Detect with ``patterns``, confirm with ``validate``, synthesise with
``generate`` — and because ``generate`` builds against the same rules
``validate`` checks, a generated identifier passes its own validator by
construction.

Everything is re-exported here, so ``from utils.czech_identifiers import
generate_ico, is_valid_rc, REGEX`` works and callers need not know which part a
name lives in. No I/O, no network, no LLM anywhere in this package.
"""

from utils.czech_identifiers.generate import (
    generate_bank_account,
    generate_dic,
    generate_iban_cz,
    iban_from_bank_account,
    generate_ico,
    generate_phone,
    generate_psc,
    generate_rc,
)
from utils.czech_identifiers.patterns import REGEX
from utils.czech_identifiers.validate import (
    ico_check_digit,
    is_valid_iban_cz,
    is_valid_ico,
    is_valid_rc,
)

__all__ = [
    # patterns — what an identifier looks like
    "REGEX",
    # validate — whether it is really one
    "ico_check_digit",
    "is_valid_ico",
    "is_valid_iban_cz",
    "is_valid_rc",
    # generate — make a fictional one
    "generate_ico",
    "generate_dic",
    "generate_iban_cz",
    "iban_from_bank_account",
    "generate_phone",
    "generate_rc",
    "generate_bank_account",
    "generate_psc",
]
