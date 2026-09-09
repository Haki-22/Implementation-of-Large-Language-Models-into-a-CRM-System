"""Module-level constants for the contact generator.

Pools, presence rates, and BFI-2 OCEAN norms, isolated here so the rest of
the package stays free of magic numbers and tuneables.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Foreign-origin name allow-list
# The generator takes the first ``n_foreign`` entries for the foreign-name
# contacts required by the spec (vocative falls back to "Dobrý den,").
# ---------------------------------------------------------------------------

_FOREIGN_NAMES = [
    {"first_name": "Nguyen", "last_name": "Tran", "gender": "m"},
    {"first_name": "Chen", "last_name": "Li", "gender": "f"},
    {"first_name": "Martin", "last_name": "Schmidt", "gender": "m"},
    {"first_name": "Fatima", "last_name": "Alves", "gender": "f"},
    {"first_name": "Ivan", "last_name": "Petrov", "gender": "m"},
]

# ---------------------------------------------------------------------------
# Titles pool: retail / customer-service / e-commerce roles.  Most contacts
# are private B2C customers with no title; B2B contacts carry a procurement /
# store-operations role.  Gendered variants applied at generation time using
# the contact's gender field.
# ---------------------------------------------------------------------------

_TITLES_POOL_M = [
    "nákupčí",
    "vedoucí prodejny",
    "skladník",
    "specialista zákaznické podpory",
    "e-shop manažer",
    "obchodní zástupce",
    "reklamační technik",
    "logistik",
    None,
    None,
    None,  # ~30% have no title (private B2C customer)
]

_TITLES_POOL_F = [
    "nákupčí",
    "vedoucí prodejny",
    "skladnice",
    "specialistka zákaznické podpory",
    "e-shop manažerka",
    "obchodní zástupkyně",
    "reklamační technička",
    "logistička",
    None,
    None,
    None,
]

# Defect labels accepted by make_defective_contact(). Each label tells the
# function which single field to null out on an otherwise valid contact:
#   - "missing_gender":    set gender = None
#   - "missing_formality": set formal = None
#   - "missing_vocative":  set name_vocative = None (gender/formal stay valid)
#   - "invalid_name":      pick first_name from _BAD_NAMES (everything else valid)
_DEFECT_TYPES = (
    "missing_gender",
    "missing_formality",
    "missing_vocative",
    "invalid_name",
)

# Pool of (first_name, last_name) pairs used by the "invalid_name" defect.
# The first name is the broken one; the last name is a normal Czech surname
# so only one field is corrupt per row.
_BAD_NAMES = [
    ("user123", "Novák"),  # placeholder username
    ("admin", "Procházka"),  # role name typed as a first name
    ("Kontaktujte prosím", "Dvořák"),  # instruction text in the name field
    ("12345", "Kopecký"),  # numeric garbage
]

# ---------------------------------------------------------------------------
# OCEAN: BFI-2 representative-sample norms (Soto & John 2017)
# 1-5 raw scale, truncated normal.
# ---------------------------------------------------------------------------

# (mean, std_dev) on the 1-5 BFI scale
_OCEAN_NORMS: dict[str, tuple[float, float]] = {
    "O": (3.75, 0.65),
    "C": (3.55, 0.70),
    "E": (3.20, 0.80),
    "A": (3.75, 0.65),
    "N": (2.85, 0.80),
}

_OCEAN_LOW: float = 1.0
_OCEAN_HIGH: float = 5.0

# ---------------------------------------------------------------------------
# PII overlay: presence rates + e-mail providers
# ---------------------------------------------------------------------------

# Per-field PII presence rates for clean contacts.  Real CRM records are
# rarely fully populated; these rates model that incompleteness while keeping
# enough coverage for downstream PII pseudonymisation tests.  The address block
# (full_street / city / postal_code / district / region) is treated atomically,
# present or absent together, because a partial address is not a realistic CRM
# defect here.
_PII_RATES: dict[str, float] = {
    "email": 0.95,
    "phone": 0.60,
    "address": 0.70,  # governs the whole address block together
    "date_of_birth": 0.20,
    "bank_account": 0.10,
    "iban": 0.05,
}

# Common Czech free e-mail providers for synthetic address generation.
_EMAIL_PROVIDERS = ("seznam.cz", "email.cz", "centrum.cz", "post.cz", "gmail.com")
