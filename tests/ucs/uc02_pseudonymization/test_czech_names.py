"""Inflected forms of Czech names for the corpus (D-UC02-1)."""

from __future__ import annotations

import pytest

from ucs.uc02_pseudonymization.code.czech_names import (
    decline_first_name,
    decline_surname,
    person_forms,
)


@pytest.mark.parametrize(
    "surname,gender,case,expected",
    [
        ("Novák", "m", "gen", "Nováka"),
        ("Novák", "m", "dat", "Novákovi"),
        ("Novák", "m", "instr", "Novákem"),
        ("Tomeš", "m", "gen", "Tomeše"),
        ("Svoboda", "m", "gen", "Svobody"),
        ("Svoboda", "m", "instr", "Svobodou"),
        ("Černý", "m", "gen", "Černého"),
        ("Krejčí", "m", "dat", "Krejčímu"),
        ("Havlíček", "m", "gen", "Havlíčka"),
        ("Slavíková", "f", "gen", "Slavíkové"),
        ("Slavíková", "f", "instr", "Slavíkovou"),
        ("Černá", "f", "instr", "Černou"),
        ("Kočí", "f", "gen", None),
    ],
)
def test_decline_surname(surname, gender, case, expected):
    assert decline_surname(surname, gender, case) == expected


@pytest.mark.parametrize(
    "first,gender,case,expected",
    [
        ("Romana", "f", "gen", "Romany"),
        ("Romana", "f", "dat", "Romaně"),
        ("Romana", "f", "instr", "Romanou"),
        ("Lenka", "f", "dat", "Lence"),
        ("Petra", "f", "dat", "Petře"),
        ("Marie", "f", "dat", "Marii"),
        ("Dagmar", "f", "gen", None),
        ("Jan", "m", "dat", "Janovi"),
        ("Jiří", "m", "gen", "Jiřího"),
        ("Pavel", "m", "gen", "Pavla"),
        ("Tomáš", "m", "instr", "Tomášem"),
    ],
)
def test_decline_first_name(first, gender, case, expected):
    assert decline_first_name(first, gender, case) == expected


def test_person_forms_offers_surname_and_full_forms():
    forms = person_forms("Romana", "Slavíková", "f")
    assert forms["nom"] == "Romana Slavíková"
    assert forms["gen_surname"] == "Slavíkové"
    assert forms["instr_full"] == "Romanou Slavíkovou"
    assert len(set(forms.values())) == len(forms)


def test_person_forms_falls_back_to_nominative_only():
    assert person_forms("Dagmar", "Kočí", "f") == {"nom": "Dagmar Kočí"}
