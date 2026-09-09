"""
Synthetic Czech contact generator for the evaluation substrate.

Domain: a fictional mixed-general Czech e-commerce retailer (elektronika,
domácnost, hračky, sport, móda, zahrada, zdraví, potraviny).  Contacts are the
retailer's customers and B2B partners.  The synthetic substrate carries no
brand name and no real person.

Generation recipe (seeded, no LLM, no network):
  - Age and sex are one joint draw from the ČSÚ age x sex table
    (``csu_sampler.sample_age_sex``), so the cohort carries the real population
    sex ratio; Faker('cs_CZ') then draws a name in the matching gendered form
    (female surnames via last_name_female(), which follows Czech grammar).
  - vokativ creates the stored vocative greeting ("Vážený pane Vávro" /
    "Ahoj Tomáši"); 70 % of contacts use the formal register. Foreign-origin
    names receive the neutral fallback 'Dobrý den,'.
  - 70 % of contacts get an OCEAN profile sampled from BFI-2 population norms
    (Soto & John 2017) with the CRMArena causal-DGP modulation; about a third
    a job title (a 45 % draw over a pool that is itself 3/11 empty); 50 % an
    affiliation with one of the eight partner companies.
  - PII fields are valid-shape but entirely fictional (e-mail 95 %, phone 60 %,
    address block 70 % -- street, city, postal code, district and region from
    one ČSÚ municipality draw -- date of birth 20 %, bank account 10 %, IBAN 5 %).
  - A deliberately defective subset (``is_clean=False``) carries one defect
    each: missing gender, missing formality, missing vocative, or a broken
    first name.

The generator produces identity and profile only. ``prior_interactions`` and
``frequent_words`` stay empty here; the assembler fills them from the
contact's translated Amazon reviews.

OCEAN generation:
  Truncated normal on the 1-5 BFI raw scale.
  Per-trait population parameters (BFI-2 representative-sample norms,
  Soto & John 2017):
    O: mu=3.75, sigma=0.65   C: mu=3.55, sigma=0.70   E: mu=3.20, sigma=0.80
    A: mu=3.75, sigma=0.65   N: mu=2.85, sigma=0.80
  Traits sampled independently (Big Five are near-orthogonal).
  Clipped to [1.0, 5.0]; round to 2 decimal places.

CRMArena causal-DGP pattern (huang2025crmarena section 3):
  Two latent variables PURCHASE_SENIORITY in [0,1] and RELATIONSHIP_WARMTH
  in [0,1] modulate the per-trait OCEAN means, giving richer covariance
  structure defensible at prototype scale.

Chain position:
  generate_contacts() -> list[dict]                   (in-memory)
  save_snapshot(contacts, path)                       (reproducible artifact)
  substrate/generators/__main__.py                    (writes the snapshot,
                                                       joined to Amazon reviewers)
  substrate/pipeline/build_substrate_db.py            (build_all step ``database``)

Package layout:
  _constants.py   pools, BFI-2 norms, presence rates
  _ocean.py       OCEAN truncated-normal sampler + CRMArena causal-DGP shift
  _vocative.py    Czech vocative greeting builder
  _pii.py         PII overlay
  _factory.py     contact factory functions + generate_contacts driver
  _snapshot.py    JSON snapshot save/load
"""

from __future__ import annotations

from ._factory import (
    generate_contact,
    generate_contacts,
    generate_foreign_contact,
    make_defective_contact,
)
from ._snapshot import _strip_private, save_snapshot

__all__ = [
    "generate_contact",
    "generate_contacts",
    "generate_foreign_contact",
    "make_defective_contact",
    "save_snapshot",
    # Snapshot helper re-exported for the tests that assert the "_"-prefixed
    # working keys never reach a committed snapshot.
    "_strip_private",
]
