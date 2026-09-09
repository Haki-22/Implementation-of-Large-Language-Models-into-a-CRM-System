"""Synthetic Czech company generator for the evaluation substrate.

The retailer's B2B partners: the companies a contact can be affiliated with
through ``Contact.company_id``. Every company carries the registry fields a
Czech CRM would hold (mirroring the public ARES register):

  - valid IČO (MOD-11 check digit per the ČSÚ algorithm)
  - DIČ as "CZ" + IČO
  - street address from Faker('cs_CZ'); city, postal code, district and region
    from one draw over the ČSÚ municipality distribution
  - legal form, taken from the suffix of the company name so name and form
    never disagree

Two ways to name the companies:

  - ``PARTNER_COMPANY_NAMES`` (default): a hand-written pool of eight
    retail-plausible partners of a mixed-general e-shop (resellers,
    distributors, suppliers). The contact generator draws affiliations from
    this pool, so the committed contacts and companies snapshots agree.
  - ``n`` random names from Faker('cs_CZ') with a sampled legal form, for
    tests and larger synthetic sets.

All output is reproducible for a fixed seed. No LLM, no network.

JSON-snapshot pipeline:
  generate_companies(seed)            → list[dict]   (in-memory)
  save_snapshot(companies, path)      → substrate/snapshots/contacts/companies.json
  build_substrate_db.py loads the snapshot and resolves Contact.company_id by name.

Import-only. The snapshot is written by ``python -m substrate.generators``,
which runs every generator in this package under one seed.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from faker import Faker

from substrate.generators.csu_sampler import sample_municipality
from utils.czech_identifiers.generate import generate_dic, generate_ico
from utils.file_safety import require_can_write
from utils.paths import COMPANIES_SNAPSHOT

# ---------------------------------------------------------------------------
# Name pool + legal forms
# ---------------------------------------------------------------------------

# Retail-plausible B2B partners of a mixed-general e-commerce retailer.
# The contact generator (substrate.generators.contacts) draws its company
# affiliations from this list; keep the two in step by importing it there.
PARTNER_COMPANY_NAMES: tuple[str, ...] = (
    "Elektro Domov s.r.o.",
    "Zahradní Centrum Morava a.s.",
    "Sportshop Distribuce s.r.o.",
    "DětskýSvět Velkoobchod s.r.o.",
    "Domácí Potřeby Plzeň a.s.",
    "Móda Trend s.r.o.",
    "Potraviny Express a.s.",
    "Zdraví a Krása s.r.o.",
)

# Most common Czech legal forms; the suffix is what appears in a company name.
_LEGAL_FORMS: tuple[str, ...] = ("s.r.o.", "a.s.", "v.o.s.", "družstvo")


def legal_form_from_name(name: str) -> str | None:
    """Return the legal form carried by a company name's suffix, if any."""
    for form in _LEGAL_FORMS:
        if name.endswith(" " + form):
            return form
    return None


def _faker_base_name(fake: Faker) -> str:
    """A Faker company name with Faker's own (sometimes obsolete) suffix stripped."""
    name = fake.company()
    for suffix in (" s.r.o.", " a.s.", " o.s.", " v.o.s.", " k.s."):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_companies(
    seed: int = 42,
    *,
    names: list[str] | tuple[str, ...] | None = None,
    n: int | None = None,
) -> list[dict]:
    """Generate synthetic Czech company dicts with registry fields.

    Args:
        seed: RNG seed for reproducibility.
        names: Company names to give registry fields to, one company per name;
            the legal form is read from the name's suffix. Defaults to
            ``PARTNER_COMPANY_NAMES`` when ``n`` is not given.
        n: Number of Faker-named companies to generate instead of ``names``.

    Returns:
        List of dicts with keys matching the Company model:
        name, ico, dic, full_street, city, postal_code, district, region, legal_form.
    """
    if names is not None and n is not None:
        raise ValueError("pass either names or n, not both")
    rng = random.Random(seed)
    fake = Faker("cs_CZ")
    Faker.seed(seed)

    if n is None:
        chosen = list(PARTNER_COMPANY_NAMES if names is None else names)
        forms = [legal_form_from_name(name) or rng.choice(_LEGAL_FORMS) for name in chosen]
    else:
        forms = [rng.choice(_LEGAL_FORMS) for _ in range(n)]
        chosen = [f"{_faker_base_name(fake)} {form}" for form in forms]

    companies: list[dict] = []
    for name, legal_form in zip(chosen, forms):
        ico = generate_ico(rng)
        municipality = sample_municipality(rng)
        companies.append(
            {
                "name": name,
                "ico": ico,
                "dic": generate_dic(ico),
                # Same street shape and the same municipality draw as a contact
                # address (generators/contacts/_pii.py), so the substrate has one
                # address format rather than two.
                "full_street": f"{fake.street_name()} {rng.randint(1, 199)}",
                "city": municipality["city"],
                "postal_code": municipality["postal_code"],
                "district": municipality["district"],
                "region": municipality["region"],
                "legal_form": legal_form,
            }
        )
    return companies


# ---------------------------------------------------------------------------
# JSON snapshot helpers
# ---------------------------------------------------------------------------


def save_snapshot(
    companies: list[dict],
    path: Path | str = COMPANIES_SNAPSHOT,
    *,
    overwrite: bool = False,
) -> None:
    """Write the generated company list to a JSON snapshot file.

    Raises:
        FileExistsError: If ``path`` exists and ``overwrite`` is ``False``.
    """
    path = require_can_write(path, overwrite=overwrite, artifact="company snapshot")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False, indent=2)
