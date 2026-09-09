"""Tests for the deterministic Czech CRM note snapshot generator."""

from __future__ import annotations

import json
from datetime import datetime

from substrate.generators.notes import _render, _templates
from substrate.generators.notes import CATEGORIES, NOTES_ANCHOR, generate_notes, save_snapshot


def _contacts() -> list[dict]:
    return [
        {
            "first_name": "Jan",
            "last_name": "Novák",
            "gender": "m",
            "phone": "+420 601 000 001",
            "email": "jan.novak@example.cz",
            "full_street": "Krátká 1",
            "city": "Brno",
            "postal_code": "60200",
            "reviewer_id": "R1",
        },
        {
            "first_name": "Eva",
            "last_name": "Svobodová",
            "gender": "f",
            "phone": "+420 601 000 002",
            "email": "eva.svobodova@example.cz",
            "full_street": "Dlouhá 2",
            "city": "Praha",
            "postal_code": "11000",
            "reviewer_id": "R2",
        },
    ]


def _verb_renderings(contact: dict, gender: str) -> set[str]:
    """Every verb-bearing template rendered for ``contact`` as if it had ``gender``."""
    as_gender = {**contact, "gender": gender}
    templates = [tpl for _, tpl in _templates._PLAIN_TEMPLATES if _render._needs_gender(tpl)]
    templates += [tpl for _, tpl, _ in _templates._PII_TEMPLATES if _render._needs_gender(tpl)]
    return {_render._render(tpl, as_gender) for tpl in templates}


def test_generate_notes_is_deterministic_and_db_shaped():
    anchor = datetime(2026, 5, 28, 12, 0, 0)
    first = generate_notes(_contacts(), seed=7, n=8, pii_rate=0.5, today=anchor)
    second = generate_notes(_contacts(), seed=7, n=8, pii_rate=0.5, today=anchor)

    assert first == second
    assert len(first) == 8
    assert {row["contact_id"] for row in first} <= {1, 2}
    assert all(row["content"] for row in first)
    assert all(row["category"] in CATEGORIES for row in first)
    assert all(row["created_at"] <= anchor.isoformat() for row in first)
    assert any("@" in row["content"] or "+420" in row["content"] for row in first)


def test_default_anchor_is_fixed():
    """Without an explicit anchor the timestamps derive from NOTES_ANCHOR, never the wall clock."""
    notes = generate_notes(_contacts(), seed=1, n=5)
    assert all(row["created_at"] <= NOTES_ANCHOR.isoformat() for row in notes)
    assert notes == generate_notes(_contacts(), seed=1, n=5, today=NOTES_ANCHOR)


def test_verbs_agree_with_gender():
    """A feminine contact gets feminine past-tense forms and never the masculine rendering."""
    eva = _contacts()[1]
    notes = generate_notes([eva], seed=3, n=60, pii_rate=0.0)
    contents = {row["content"] for row in notes}
    assert contents & _verb_renderings(eva, "f")
    assert not contents & _verb_renderings(eva, "m")


def test_unknown_gender_gets_only_verb_free_templates():
    contact = {**_contacts()[0], "gender": None}
    notes = generate_notes([contact], seed=5, n=40, pii_rate=0.5)
    contents = {row["content"] for row in notes}
    assert contents
    assert not contents & _verb_renderings(contact, "m")
    assert not contents & _verb_renderings(contact, "f")


def test_pii_notes_only_use_fields_the_contact_has():
    """No phone, e-mail or address is invented for a contact that lacks them."""
    bare = {"first_name": "Petr", "last_name": "Král", "gender": "m", "reviewer_id": None}
    notes = generate_notes([bare], seed=11, n=40, pii_rate=1.0)
    texts = " ".join(row["content"] for row in notes)
    assert "+420" not in texts
    assert "@" not in texts
    assert "None" not in texts


def test_save_snapshot_writes_notes(tmp_path):
    notes = generate_notes(_contacts(), seed=3, n=3, pii_rate=0.0)
    out = tmp_path / "notes.json"
    save_snapshot(notes, out)

    assert json.loads(out.read_text(encoding="utf-8")) == notes
