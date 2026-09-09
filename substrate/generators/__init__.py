"""Synthetic data generators for the Czech CRM evaluation substrate.

The substrate is the one shared snapshot every evaluation reads from.  This
package produces its synthetic layer deterministically from seeded RNG. No
generator here calls an LLM or the network.

Submodules
----------

``contacts``
    Czech contact factory (names, vocative, gender, formality, OCEAN, PII).
    Split internally into ``_factory``, ``_constants``, ``_snapshot``,
    ``_vocative``, ``_pii``, ``_ocean``.  See ``contacts/__init__.py`` for the
    full recipe.

``companies``
    The retailer's partner companies with checksum-valid IČO / DIČ, one ČSÚ
    address draw (city, postal code, district, region), and the legal form
    read from the name.

``notes``
    Seeded Czech CRM-note rows: the writable activity surface UC-03 reads and
    appends to, and short Czech text quoting the contact's own personal data.

``csu_sampler``
    Seeded samplers over Czech demographic distributions (age, sex,
    municipality), grounded in public Czech Statistical Office (ČSÚ) data
    bundled in ``data/cz_*.csv``.

Determinism
-----------

Every public function in this package either accepts an explicit
``random.Random`` instance or an integer ``seed``.  Output is fully
reproducible for a fixed seed; do not rely on the global RNG.

I/O
---

Snapshots are JSON files under ``substrate/snapshots/``; the ``save_snapshot``
helpers refuse to overwrite unless ``overwrite=True``. Importing this package
writes nothing.

Running it does: ``python -m substrate.generators --force`` runs every generator
under one seed and writes the three ``contacts/`` snapshots together (see
``__main__.py``). ``substrate.pipeline.build_all`` calls it as step ``contacts``.
"""

from substrate.generators.companies import generate_companies, legal_form_from_name
from substrate.generators.contacts import generate_contacts
from substrate.generators.csu_sampler import (
    birth_date_for_age,
    sample_age,
    sample_age_sex,
    sample_municipality,
)
from substrate.generators.notes import generate_notes

__all__ = [
    # identity layer
    "generate_contacts",
    "generate_companies",
    "generate_notes",
    "legal_form_from_name",
    # demographic draws behind them
    "sample_age_sex",
    "sample_age",
    "birth_date_for_age",
    "sample_municipality",
]
