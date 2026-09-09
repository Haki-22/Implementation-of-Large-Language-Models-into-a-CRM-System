"""Tests for substrate.generators.contacts: generate_contacts() with the retail theme.

The thesis substrate is a fictional mixed-general Czech e-commerce retailer.
These tests assert that clean contacts carry a PII layer at the prescribed
presence rates, that names are unique, and that the generator writes no free
text (that is the assembler's job, from the translated reviews).
"""

import pytest

from substrate.generators.contacts import generate_contacts, save_snapshot


def test_contacts_have_pii_at_rates():
    cs = generate_contacts(seed=42, n_clean=180, n_non_clean=20, n_foreign=2)
    assert len(cs) == 200
    clean = [c for c in cs if c["is_clean"]]

    def rate(field: str) -> float:
        return sum(1 for c in clean if c.get(field)) / len(clean)

    assert 0.88 <= rate("email") <= 1.0
    assert 0.45 <= rate("phone") <= 0.75
    assert 0.10 <= rate("date_of_birth") <= 0.30


def test_counts_are_exact_and_names_unique():
    cs = generate_contacts(seed=7, n_clean=450, n_non_clean=50, n_foreign=2)
    assert len(cs) == 500
    clean = [c for c in cs if c["is_clean"]]
    assert len(clean) == 450 and sum(1 for c in cs if not c["is_clean"]) == 50
    names = [(c["first_name"], c["last_name"]) for c in clean]
    assert len(set(names)) == len(names)
    assert sum(1 for c in clean if c["_foreign_origin"]) == 2


def test_generator_writes_no_free_text():
    cs = generate_contacts(seed=3, n_clean=20, n_non_clean=2, n_foreign=1)
    assert all(c["prior_interactions"] is None for c in cs)
    assert all(c["frequent_words"] is None for c in cs)


def test_defective_contacts_cover_all_defect_types():
    cs = generate_contacts(seed=5, n_clean=10, n_non_clean=8, n_foreign=0)
    defective = [c for c in cs if not c["is_clean"]]
    assert len(defective) == 8
    assert all(c["name_vocative"] is None for c in defective)
    assert any(c["gender"] is None for c in defective)
    assert any(c["formal"] is None for c in defective)
    assert any(
        c["first_name"] in {"user123", "admin", "Kontaktujte prosím", "12345"} for c in defective
    )


def test_generate_contacts_is_deterministic():
    assert generate_contacts(seed=11, n_clean=30, n_non_clean=3, n_foreign=2) == generate_contacts(
        seed=11, n_clean=30, n_non_clean=3, n_foreign=2
    )


def test_save_snapshot_refuses_overwrite(tmp_path):
    path = tmp_path / "contacts.json"
    contacts = generate_contacts(seed=2, n_clean=5, n_non_clean=1, n_foreign=1)
    save_snapshot(contacts, path)

    with pytest.raises(FileExistsError, match="--force"):
        save_snapshot(contacts, path)

    save_snapshot(contacts, path, overwrite=True)
