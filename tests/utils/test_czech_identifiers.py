"""Czech PII generator tests — ICO / DIC / RC checksum + format invariants."""

import random

import pytest
from utils.czech_identifiers import (
    is_valid_rc,
    ico_check_digit,
    generate_ico,
    generate_dic,
    generate_iban_cz,
    generate_phone,
    generate_rc,
    generate_bank_account,
    generate_psc,
)


def test_ico_check_digit_known_value():
    # IČO 25596641: first 7 = 2559664, check digit = 1
    assert ico_check_digit("2559664") == 1


def test_generate_ico_is_8_digits_and_self_consistent():
    rng = random.Random(1)
    ico = generate_ico(rng)
    assert len(ico) == 8 and ico.isdigit()
    assert ico_check_digit(ico[:7]) == int(ico[7])


def test_generate_dic_prefixes_cz():
    assert generate_dic("25596641") == "CZ25596641"


def test_generate_iban_cz_mod97():
    rng = random.Random(2)
    iban = generate_iban_cz(rng)
    compact = iban.replace(" ", "")
    assert compact.startswith("CZ") and len(compact) == 24
    rearranged = compact[4:] + compact[:4]
    num = "".join(str(int(c, 36)) for c in rearranged)
    assert int(num) % 97 == 1


def test_generate_phone_czech_mobile():
    rng = random.Random(3)
    phone = generate_phone(rng)
    assert phone.startswith("+420 ")
    digits = phone.replace("+420 ", "").replace(" ", "")
    assert len(digits) == 9 and digits[0] in "67"


def test_generate_rc_divisible_by_11():
    rng = random.Random(4)
    rc = generate_rc(1985, 3, "f", rng)  # year, month, sex
    digits = rc.replace("/", "")
    assert len(digits) == 10
    assert int(digits) % 11 == 0
    assert int(digits[2:4]) == 3 + 50  # woman: month + 50


def test_generate_bank_account_domestic_format():
    rng = random.Random(5)
    acc = generate_bank_account(rng)
    body, bank = acc.split("/")
    assert bank.isdigit() and len(bank) == 4


def test_generate_psc_5_digits():
    rng = random.Random(6)
    psc = generate_psc(rng)
    assert psc.replace(" ", "").isdigit() and len(psc.replace(" ", "")) == 5


# ---------------------------------------------------------------------------
# is_valid_rc — the rules a Czech rodné číslo actually follows
#
# UC-02's pseudonymiser gates every RC-shaped regex match on this function, so a
# rule it gets wrong is either a missed identifier (a privacy failure) or a
# false positive in the reported numbers. Cases below are built to satisfy the
# mod-11 check digit, so each one tests the rule it is named for and nothing else.
# ---------------------------------------------------------------------------


def _rc_with_valid_check_digit(yy: int, mm: int, dd: int, serial: int = 123) -> str | None:
    """Build 'YYMMDD/SSSC' whose ten digits are divisible by 11, or None."""
    prefix = f"{yy:02d}{mm:02d}{dd:02d}{serial:03d}"
    for check in range(10):
        if int(prefix + str(check)) % 11 == 0:
            return prefix[:6] + "/" + prefix[6:] + str(check)
    return None


@pytest.mark.parametrize(
    "month_field, label",
    [
        (1, "men, plain month"),
        (21, "men, +20 exhausted sequence"),
        (51, "women, +50"),
        (71, "women, +50 and +20 exhausted sequence"),
    ],
)
def test_is_valid_rc_accepts_every_legal_month_band(month_field: int, label: str):
    """Men 01-12 / 21-32, women 51-62 / 71-82 (zákon č. 53/2004 Sb.)."""
    value = _rc_with_valid_check_digit(85, month_field, 15)
    assert value is not None
    assert is_valid_rc(value), f"{label}: {value} should be valid"


@pytest.mark.parametrize("month_field", [33, 63, 83])
def test_is_valid_rc_rejects_months_outside_the_legal_bands(month_field: int):
    value = _rc_with_valid_check_digit(85, month_field, 15)
    assert value is not None
    assert not is_valid_rc(value)


def test_is_valid_rc_accepts_the_historical_remainder_10_exception():
    """No digit 0-9 satisfies a remainder of 10, so the check digit was 0.

    The full number is then NOT divisible by 11. About a thousand were issued;
    issuance stopped in 1985. Rejecting them would drop real identifiers.
    """
    value = "850115/0010"
    assert int(value.replace("/", "")[:9]) % 11 == 10
    assert is_valid_rc(value)


def test_is_valid_rc_rejects_a_wrong_check_digit():
    good = _rc_with_valid_check_digit(85, 5, 15)
    assert good is not None
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert is_valid_rc(good) and not is_valid_rc(bad)


def test_is_valid_rc_short_form_does_not_reject_29_february():
    """The pre-1954 nine-digit form carries no century, so a 29th is unresolvable.

    Guessing a century to reject the date would drop valid numbers; the day is
    range-checked instead.
    """
    assert is_valid_rc("000229/123")
    assert not is_valid_rc("701320/123")  # month 13 is in no legal band


def test_generated_rc_always_passes_its_own_validator():
    """generate builds against the rules validate checks."""
    rng = random.Random(7)
    for year in (1950, 1985, 2001):
        for month in (1, 2, 12):
            for sex in ("m", "f"):
                assert is_valid_rc(generate_rc(year, month, sex, rng))


def test_iban_from_bank_account_encodes_the_same_account():
    """A contact that stores both fields stores one account in two notations (D-DB-2)."""
    from utils.czech_identifiers import iban_from_bank_account, is_valid_iban_cz

    iban = iban_from_bank_account("19-2000145399/0800")
    assert iban == "CZ65 0800 0000 1920 0014 5399"
    assert is_valid_iban_cz(iban)
    assert iban_from_bank_account("79026-44/0800").replace(" ", "")[4:8] == "0800"
    assert is_valid_iban_cz(iban_from_bank_account("729597320/5500"))
    with pytest.raises(ValueError):
        iban_from_bank_account("not an account")
