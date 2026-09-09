"""Tests for substrate.generators.companies — generate_companies()."""

import pytest

from substrate.generators.companies import (
    PARTNER_COMPANY_NAMES,
    generate_companies,
    legal_form_from_name,
    save_snapshot,
)
from utils.czech_identifiers import ico_check_digit, is_valid_ico


def _assert_registry_fields(company: dict) -> None:
    assert company["legal_form"] in {"s.r.o.", "a.s.", "v.o.s.", "družstvo"}
    assert len(company["ico"]) == 8 and ico_check_digit(company["ico"][:7]) == int(
        company["ico"][7]
    )
    assert is_valid_ico(company["ico"])
    assert company["dic"] == "CZ" + company["ico"]
    assert company["city"] and company["postal_code"] and company["full_street"]


def test_default_is_the_partner_pool_with_registry_fields():
    cos = generate_companies(seed=42)
    assert [c["name"] for c in cos] == list(PARTNER_COMPANY_NAMES)
    for c in cos:
        _assert_registry_fields(c)
        assert c["legal_form"] == legal_form_from_name(c["name"])


def test_generate_random_companies_valid_and_consistent():
    cos = generate_companies(seed=42, n=12)
    assert len(cos) == 12
    for c in cos:
        _assert_registry_fields(c)
        assert c["name"].endswith(" " + c["legal_form"])


def test_generate_companies_deterministic():
    assert generate_companies(seed=1, n=5) == generate_companies(seed=1, n=5)
    assert generate_companies(seed=1) == generate_companies(seed=1)


def test_names_and_n_are_exclusive():
    with pytest.raises(ValueError):
        generate_companies(seed=1, names=["Firma s.r.o."], n=2)


def test_save_snapshot_refuses_overwrite(tmp_path):
    path = tmp_path / "companies.json"
    companies = generate_companies(seed=3, n=2)
    save_snapshot(companies, path)

    with pytest.raises(FileExistsError, match="--force"):
        save_snapshot(companies, path)

    save_snapshot(companies, path, overwrite=True)
