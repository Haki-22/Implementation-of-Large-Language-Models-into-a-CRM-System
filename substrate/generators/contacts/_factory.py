"""Synthetic contact factory functions.

Builds one contact at a time (Czech clean / foreign-origin / deliberately
defective), plus the orchestrating ``generate_contacts()`` driver which mixes
all three flavours and keeps clean names unique.

The generator produces identity and profile only. The two free-text fields
``prior_interactions`` and ``frequent_words`` are left ``None`` here; the
substrate assembler (``substrate/pipeline/build_substrate_db.py``) fills them
from the contact's translated Amazon reviews.
"""

from __future__ import annotations

import random
from typing import Optional

from faker import Faker

from substrate.generators import csu_sampler
from substrate.generators.companies import PARTNER_COMPANY_NAMES

from ._constants import (
    _BAD_NAMES,
    _DEFECT_TYPES,
    _FOREIGN_NAMES,
    _TITLES_POOL_F,
    _TITLES_POOL_M,
)
from ._ocean import _make_ocean_from_latent
from ._pii import _make_pii
from ._vocative import _build_vocative


# ---------------------------------------------------------------------------
# Name drawing
# ---------------------------------------------------------------------------


def _czech_name_for_gender(fake: Faker, gender: str) -> tuple[str, str]:
    """Pick a Czech name matching an already-decided gender.

    The gender itself comes from the ČSÚ age x sex table (see
    ``csu_sampler.sample_age_sex``), not from a coin flip, so the cohort carries
    the real population ratio.

    Args:
        fake: Faker('cs_CZ') instance, provides first/last name pools.
        gender: "m" or "f".

    Returns:
        (first_name, last_name) in the matching gendered form.
    """
    if gender == "f":
        return fake.first_name_female(), fake.last_name_female()
    return fake.first_name_male(), fake.last_name_male()


# ---------------------------------------------------------------------------
# Contact shape
# ---------------------------------------------------------------------------


def _blank_contact() -> dict:
    """The full Contact-shaped dict with every optional field empty."""
    return {
        "first_name": None,
        "last_name": None,
        "nickname": None,
        "gender": None,
        "formal": None,
        "name_vocative": None,
        "company_id": None,
        "_company_name": None,
        "title": None,
        "ocean": None,
        "purchase_seniority": None,
        "relationship_warmth": None,
        "frequent_words": None,
        "prior_interactions": None,
        "email": None,
        "phone": None,
        "full_street": None,
        "city": None,
        "postal_code": None,
        "district": None,
        "region": None,
        "date_of_birth": None,
        "bank_account": None,
        "iban": None,
        "is_clean": True,
        # Filled by the runner's pairing step (substrate/generators/__main__.py):
        # the reviewer behind the history, its inferred gender, and whether that
        # gender matches this contact's. Prospects keep the blanks.
        "reviewer_id": None,
        "amazon_group": None,
        "reviewer_gender": None,
        "gender_paired": False,
        "_foreign_origin": False,
    }


# ---------------------------------------------------------------------------
# Czech clean contact
# ---------------------------------------------------------------------------


def generate_contact(
    rng: random.Random,
    fake: Faker,
    company_names: Optional[list[str] | tuple[str, ...]] = None,
) -> dict:
    """Build one clean Czech contact dict.

    Args:
        rng: Seeded RNG for reproducibility.
        fake: Faker('cs_CZ') instance.
        company_names: Pool to draw a company affiliation from. Defaults to
            ``substrate.generators.companies.PARTNER_COMPANY_NAMES``, the same
            pool the company generator gives registry fields to; the order must
            not change, the seeded draw picks by index.

    Returns:
        Contact dict with name, gender, formal, vocative, optional
        ocean/title/company, and the PII overlay.
    """
    if company_names is None:
        company_names = PARTNER_COMPANY_NAMES

    age, gender = csu_sampler.sample_age_sex(rng)
    first_name, last_name = _czech_name_for_gender(fake, gender)
    is_woman = gender == "f"
    formal = rng.random() < 0.70  # 70% formal, Czech B2B convention

    nickname = first_name if (not formal and rng.random() < 0.20) else None
    name_vocative = _build_vocative(first_name, last_name, gender, formal)

    # CRMArena latent variables that bias OCEAN sampling.
    purchase_seniority = rng.uniform(0.1, 1.0)
    relationship_warmth = rng.uniform(0.1, 1.0)

    # Three independent presence flags: 70% have OCEAN, 45% have title, 50% have company.
    has_ocean = rng.random() < 0.70
    has_title = rng.random() < 0.45
    has_company = rng.random() < 0.50

    ocean_dict = (
        _make_ocean_from_latent(purchase_seniority, relationship_warmth, rng) if has_ocean else None
    )
    title = rng.choice(_TITLES_POOL_F if is_woman else _TITLES_POOL_M) if has_title else None
    company_name = rng.choice(company_names) if has_company else None

    contact = {
        **_blank_contact(),
        "first_name": first_name,
        "last_name": last_name,
        "nickname": nickname,
        "gender": gender,
        "formal": formal,
        "name_vocative": name_vocative,
        "_company_name": company_name,
        "title": title,
        "ocean": ocean_dict,
        "purchase_seniority": round(purchase_seniority, 3),
        "relationship_warmth": round(relationship_warmth, 3),
    }
    contact.update(_make_pii(rng, age=age, first_name=first_name, last_name=last_name, fake=fake))
    return contact


# ---------------------------------------------------------------------------
# Foreign-origin contact
# ---------------------------------------------------------------------------


def generate_foreign_contact(
    rng: random.Random,
    fake: Faker,
    foreign_name_entry: dict,
) -> dict:
    """Build one foreign-origin clean contact dict.

    Args:
        rng: Seeded RNG for reproducibility.
        fake: Faker('cs_CZ') instance (used only for the PII overlay).
        foreign_name_entry: One entry from _FOREIGN_NAMES with keys
            first_name, last_name, gender.

    Returns:
        Contact dict with formal=True, name_vocative="Dobrý den,",
        _foreign_origin=True, ocean populated, and the PII overlay.
    """
    first_name = foreign_name_entry["first_name"]
    last_name = foreign_name_entry["last_name"]
    gender = foreign_name_entry["gender"]

    # Narrower OCEAN range (0.3-0.9 vs 0.1-1.0 for natives) keeps foreign
    # contacts closer to the middle of the distribution.
    seniority = rng.uniform(0.3, 0.9)
    warmth = rng.uniform(0.3, 0.9)
    ocean = _make_ocean_from_latent(seniority, warmth, rng)
    age = csu_sampler.sample_age(rng, sex=gender)

    contact = {
        **_blank_contact(),
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "formal": True,
        "name_vocative": "Dobrý den,",
        "ocean": ocean,
        "purchase_seniority": round(seniority, 3),
        "relationship_warmth": round(warmth, 3),
        "_foreign_origin": True,
    }
    contact.update(_make_pii(rng, age=age, first_name=first_name, last_name=last_name, fake=fake))
    return contact


# ---------------------------------------------------------------------------
# Deliberately defective contact
# ---------------------------------------------------------------------------


def make_defective_contact(
    rng: random.Random,
    fake: Faker,
    defect_type: str,
) -> dict:
    """Build one deliberately defective contact dict.

    Args:
        rng: Seeded RNG for reproducibility.
        fake: Faker('cs_CZ') instance.
        defect_type: One of _DEFECT_TYPES. Determines which field is nulled
            ("missing_gender" / "missing_formality" / "missing_vocative") or
            whether first_name is pulled from _BAD_NAMES ("invalid_name").

    Returns:
        Contact dict with is_clean=False, the requested field nulled, and a
        partial PII overlay (presence rates still apply).

    Raises:
        ValueError: If defect_type is not in _DEFECT_TYPES.
    """
    if defect_type not in _DEFECT_TYPES:
        raise ValueError(f"Unknown defect_type: {defect_type!r}. Use one of {_DEFECT_TYPES}.")

    if defect_type == "invalid_name":
        first_name, last_name = rng.choice(_BAD_NAMES)
        age, gender = csu_sampler.sample_age_sex(rng)
        formal = rng.choice([True, False])
    else:
        age, gender = csu_sampler.sample_age_sex(rng)
        first_name, last_name = _czech_name_for_gender(fake, gender)
        formal = rng.choice([True, False])

    # Apply the requested defect: overwrite a single field with None.
    if defect_type == "missing_gender":
        gender = None
    elif defect_type == "missing_formality":
        formal = None
    # "missing_vocative" and "invalid_name" keep gender + formal; vocative is
    # always None for defective contacts.

    contact = {
        **_blank_contact(),
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "formal": formal,
        "is_clean": False,
    }
    # Partial PII overlay: presence rates still apply, defect fields stay defective.
    # The age is the pre-defect draw, so a nulled gender does not also lose the age.
    contact.update(_make_pii(rng, age=age, first_name=first_name, last_name=last_name, fake=fake))
    return contact


# ---------------------------------------------------------------------------
# Cohort driver
# ---------------------------------------------------------------------------


def generate_contacts(
    seed: int,
    n_clean: int,
    n_non_clean: int,
    n_foreign: int,
) -> list[dict]:
    """
    Generate a list of synthetic contact dicts ready for the snapshot.

    OCEAN values are on the 1-5 BFI raw scale (truncated normal, BFI-2 norms).
    Clean contacts also carry a PII overlay (email, phone, address block,
    date_of_birth, bank_account, iban) at the rates fixed in _PII_RATES;
    non-clean contacts may carry a partial overlay. Clean contacts have unique
    (first_name, last_name) pairs: a duplicate draw is discarded and redrawn,
    so the requested counts are always met.

    Every argument is required on purpose. The substrate's own numbers -- 500
    contacts, a 90 / 10 clean / defective split, 2 foreign, seed 42 -- live in
    one place, the runner ``substrate/generators/__main__.py``; this function
    takes no position on them, so they cannot drift between two definitions.

    Args:
        seed: RNG seed for reproducibility.
        n_clean: Number of clean contacts (gender + formality + vocative set).
        n_non_clean: Number of deliberately non-clean contacts.
        n_foreign: Number of foreign-origin contacts (included in n_clean).

    Returns:
        List of exactly ``n_clean + n_non_clean`` dicts matching the Contact
        field schema: foreign-origin first, then Czech clean, then defective.
    """
    if n_foreign > len(_FOREIGN_NAMES):
        raise ValueError(
            f"n_foreign={n_foreign} exceeds the {len(_FOREIGN_NAMES)}-name foreign pool"
        )
    if n_foreign > n_clean:
        raise ValueError("n_foreign must not exceed n_clean")

    rng = random.Random(seed)
    fake = Faker("cs_CZ")
    Faker.seed(seed)

    contacts: list[dict] = []
    seen_names: set[tuple[str, str]] = set()

    # --- Foreign-origin contacts (subset of clean) ---
    for entry in _FOREIGN_NAMES[:n_foreign]:
        c = generate_foreign_contact(rng, fake, entry)
        seen_names.add((c["first_name"], c["last_name"]))
        contacts.append(c)

    # --- Clean Czech-origin contacts, unique by full name ---
    n_native_clean = n_clean - n_foreign
    native: list[dict] = []
    while len(native) < n_native_clean:
        c = generate_contact(rng, fake, PARTNER_COMPANY_NAMES)
        key = (c["first_name"], c["last_name"])
        if key in seen_names:
            continue
        seen_names.add(key)
        native.append(c)
    contacts.extend(native)

    # --- Deliberately non-clean contacts ---
    # The four defect types are repeated round-robin and truncated to
    # n_non_clean, so the subset scales with the requested count.
    non_clean_types = [_DEFECT_TYPES[i % len(_DEFECT_TYPES)] for i in range(n_non_clean)]
    rng.shuffle(non_clean_types)
    for nc_type in non_clean_types:
        contacts.append(make_defective_contact(rng, fake, nc_type))

    return contacts
