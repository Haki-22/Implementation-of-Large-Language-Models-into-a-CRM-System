"""Turn one template and one contact row into a note.

Handles the three things that make a rendered note correct: the placeholders a
template uses, whether the contact can satisfy them, and Czech gender agreement
on the past-tense verb ("dotazoval" / "dotazovala"). A contact whose gender is
unknown -- the deliberately defective rows -- only ever gets a template without
a gender-bearing verb, so the substrate never puts a guessed gender in writing.
"""

from __future__ import annotations

import random
import string
from typing import Any

from ._templates import _PII_TEMPLATES, _PLAIN_TEMPLATES, _VERBS

_FORMATTER = string.Formatter()


# ---------------------------------------------------------------------------
# Template introspection
# ---------------------------------------------------------------------------


def _fields(template: str) -> set[str]:
    """Return the set of placeholder names used by a template."""
    return {field for _, field, _, _ in _FORMATTER.parse(template) if field}


def _needs_gender(template: str) -> bool:
    """Return whether `template` uses at least one gender-bearing verb slot."""
    return bool(_fields(template) & _VERBS.keys())


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _contact_name(contact: dict[str, Any]) -> tuple[str, str]:
    """Return `(first_name, last_name)`, falling back to "Zákazník" / "" when unset."""
    return str(contact.get("first_name") or "Zákazník"), str(contact.get("last_name") or "")


def _render(template: str, contact: dict[str, Any]) -> str:
    """Fill `template`'s placeholders from `contact`, choosing verb gender from `contact["gender"]`.

    Every gender-bearing verb slot in `_VERBS` is made available under its own
    name (masculine or feminine form, depending on `contact["gender"]`),
    alongside the name and PII placeholders (`first`, `full`, `phone`,
    `email`, `street`, `city`, `postal`, `reviewer`). Caller must already have
    checked eligibility (`_eligible_plain` / `_eligible_pii`) so every
    placeholder the template references resolves to a real value.
    """
    first, last = _contact_name(contact)
    gender = contact.get("gender")
    verbs = {slot: (fem if gender == "f" else masc) for slot, (masc, fem) in _VERBS.items()}
    return template.format(
        first=first,
        full=f"{first} {last}".strip(),
        phone=contact.get("phone"),
        email=contact.get("email"),
        street=contact.get("full_street"),
        city=contact.get("city"),
        postal=contact.get("postal_code"),
        reviewer=contact.get("reviewer_id"),
        **verbs,
    )


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def _eligible_plain(contact: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the `_PLAIN_TEMPLATES` usable for `contact` (all of them if its gender is known)."""
    if contact.get("gender") in ("m", "f"):
        return list(_PLAIN_TEMPLATES)
    return [(cat, tpl) for cat, tpl in _PLAIN_TEMPLATES if not _needs_gender(tpl)]


def _eligible_pii(contact: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the `_PII_TEMPLATES` whose required fields `contact` has (and whose gender need, if any, is met)."""
    has_gender = contact.get("gender") in ("m", "f")
    out = []
    for cat, tpl, required in _PII_TEMPLATES:
        if not all(contact.get(field) for field in required):
            continue
        if _needs_gender(tpl) and not has_gender:
            continue
        out.append((cat, tpl))
    return out


def _render_note(contact: dict[str, Any], rng: random.Random, *, pii: bool) -> tuple[str, str]:
    """Return ``(category, content)`` for one note.

    A PII note falls back to a plain note when the contact has none of the
    fields the PII templates need.
    """
    pool = _eligible_pii(contact) if pii else []
    if not pool:
        pool = _eligible_plain(contact)
    category, template = rng.choice(pool)
    return category, _render(template, contact)
