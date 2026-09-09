"""PII overlay for synthetic contacts.

Generates valid-shape but entirely fictional Czech identifiers (e-mail, phone,
address, date of birth, bank account, IBAN) for contacts. Each field is present
only at the rate fixed in ``_PII_RATES`` so the synthetic records mirror the
sparse population typical of real CRM extracts.

The contact's age is decided by the caller (drawn from the ČSÚ age x sex table
together with the sex), so every contact has a real age behind it even though
only ``_PII_RATES["date_of_birth"]`` of them expose a birth date as a stored
identifier -- a CRM rarely knows everyone's birthday.
"""

from __future__ import annotations

import random
import unicodedata
from typing import Optional

from faker import Faker

from substrate.generators import csu_sampler
from utils.czech_identifiers.generate import (
    generate_bank_account,
    generate_iban_cz,
    generate_phone,
    iban_from_bank_account,
)

from ._constants import _EMAIL_PROVIDERS, _PII_RATES


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _ascii_fold(text: str) -> str:
    """ASCII-fold a Czech string for use in an e-mail local part.

    Strips diacritics (NFKD decomposition + combining-mark removal), lowercases,
    and drops any remaining non-alphanumeric character.  'Žofie' -> 'zofie'.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in stripped.lower() if ch.isalnum())


def _make_email(rng: random.Random, first_name: str, last_name: str) -> str:
    """Build a Czech-looking 'jmeno.prijmeni@<provider>' e-mail address.

    Both name parts are ASCII-folded so the address is a valid local part.
    A small random integer suffix is appended ~40% of the time to avoid
    collisions and mimic real-world address shapes ('jan.novak42@seznam.cz').
    """
    local_first = _ascii_fold(first_name) or "kontakt"
    local_last = _ascii_fold(last_name) or "uzivatel"
    suffix = str(rng.randint(1, 99)) if rng.random() < 0.40 else ""
    provider = rng.choice(_EMAIL_PROVIDERS)
    return f"{local_first}.{local_last}{suffix}@{provider}"


# ---------------------------------------------------------------------------
# PII overlay
# ---------------------------------------------------------------------------


def _make_pii(
    rng: random.Random,
    age: int,
    first_name: str = "",
    last_name: str = "",
    fake: Optional[Faker] = None,
) -> dict:
    """Generate the PII overlay for one contact.

    Produces valid-shape but entirely fictional Czech identifiers, each present
    only at the rate fixed in _PII_RATES.  All randomness is driven by the
    passed-in seeded ``rng`` so the overlay is reproducible.

    Args:
        rng: Seeded random instance.
        age: The contact's age at ``SUBSTRATE_REFERENCE_DATE``, drawn by the
            caller from the ČSÚ table; turned into a birth date when the
            date_of_birth presence check passes.
        first_name: Contact first name, folded into the e-mail local part.
        last_name: Contact last name, folded into the e-mail local part.
        fake: Optional shared Faker('cs_CZ') instance for street generation.
            A fresh one is created when omitted.

    Returns:
        A dict carrying the PII fields actually present for this contact.
        Absent fields are simply omitted (callers merge with .update()).
    """
    if fake is None:
        fake = Faker("cs_CZ")

    pii: dict = {}

    if rng.random() < _PII_RATES["email"]:
        pii["email"] = _make_email(rng, first_name, last_name)

    if rng.random() < _PII_RATES["phone"]:
        pii["phone"] = generate_phone(rng)

    # Address, generated and stored as an atomic unit: street, municipality and
    # the district + region that municipality belongs to.
    if rng.random() < _PII_RATES["address"]:
        municipality = csu_sampler.sample_municipality(rng)
        pii["full_street"] = f"{fake.street_name()} {rng.randint(1, 199)}"
        pii["city"] = municipality["city"]
        pii["postal_code"] = municipality["postal_code"]
        pii["district"] = municipality["district"]
        pii["region"] = municipality["region"]

    if rng.random() < _PII_RATES["date_of_birth"]:
        # Store a native datetime.date; SQLAlchemy's Date column requires it.
        # save_snapshot() serialises it to an ISO string for the JSON artifact.
        pii["date_of_birth"] = csu_sampler.birth_date_for_age(rng, age)

    if rng.random() < _PII_RATES["bank_account"]:
        pii["bank_account"] = generate_bank_account(rng)

    if rng.random() < _PII_RATES["iban"]:
        # The draw stays so the random stream (and every other contact) is
        # unchanged; a contact that also stores a domestic account gets the IBAN
        # of that account instead of an unrelated one (D-DB-2).
        drawn = generate_iban_cz(rng)
        pii["iban"] = (
            iban_from_bank_account(pii["bank_account"]) if "bank_account" in pii else drawn
        )

    return pii
