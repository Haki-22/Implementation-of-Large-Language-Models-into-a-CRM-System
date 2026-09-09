"""Seeded generators for valid-shape, entirely fictional Czech identifiers.

The half the substrate uses to build synthetic people and companies, and UC-02's
corpus builder uses to plant identifiers it can then try to detect. Every value
is constructed with the same rules :mod:`utils.czech_identifiers.validate`
checks, so a generated identifier passes its own validator by construction.

Nothing here is real: the checksums are correct, the holders are not.

Pure and seeded — every function takes a ``random.Random`` so callers pin their
own reproducibility. No I/O, no network, no LLM.
"""

from __future__ import annotations

from random import Random

from utils.czech_identifiers.validate import _days_in_month, ico_check_digit

# ---------------------------------------------------------------------------
# IČO + DIČ
# ---------------------------------------------------------------------------


def generate_ico(rng: Random) -> str:
    """Generate a syntactically valid 8-digit IČO string."""
    # First digit 1-9 (no leading zero in real IČOs)
    first = str(rng.randint(1, 9))
    rest = "".join(str(rng.randint(0, 9)) for _ in range(6))
    seven = first + rest
    return seven + str(ico_check_digit(seven))


def generate_dic(ico: str) -> str:
    """Return the legal-entity DIČ form used when the VAT number is 'CZ' + IČO.

    Not every Czech DIČ is derivable from an IČO; this is the common company case
    the substrate needs.
    """
    return "CZ" + ico


_IBAN_BANK_CODES = (
    "0100",
    "0300",
    "0600",
    "0800",
    "2010",
    "3030",
    "5500",
    "6210",
)


def _iban_from_bban(bban: str) -> str:
    """Return the Czech IBAN of a 20-digit BBAN (bank code, prefix, account) in print format.

    ISO 7064 MOD-97-10: move "CZ00" to the end, convert to an integer, the check
    digits are ``98 - (number mod 97)``, zero-padded to two digits.
    """
    if len(bban) != 20 or not bban.isdigit():
        raise ValueError(f"a Czech BBAN has 20 digits, got {bban!r}")
    rearranged = bban + "CZ00"
    num_str = "".join(str(int(c, 36)) for c in rearranged)
    kk = str(98 - (int(num_str) % 97)).zfill(2)
    raw = "CZ" + kk + bban  # 24 chars
    return " ".join(raw[i : i + 4] for i in range(0, 24, 4))


def generate_iban_cz(rng: Random) -> str:
    """Generate a syntactically valid Czech IBAN (ISO 7064 MOD-97-10).

    Structure: CZ kk bbbb pppppp aaaaaaaaaa
        kk   — 2-digit check digits
        bbbb — 4-digit bank code
        pppppp — 6-digit account prefix (may be 000000)
        aaaaaaaaaa — 10-digit account number
    """
    bank = rng.choice(_IBAN_BANK_CODES)
    prefix = str(rng.randint(0, 999999)).zfill(6)
    account = str(rng.randint(1, 9_999_999_999)).zfill(10)
    return _iban_from_bban(bank + prefix + account)


def iban_from_bank_account(account: str) -> str:
    """Return the IBAN that encodes a domestic account ``[prefix-]number/bank``.

    The two are the same account in two notations: the IBAN's BBAN is the bank
    code, the prefix zero-padded to six digits and the number zero-padded to
    ten. A contact that stores both therefore stores one account (D-DB-2).
    """
    local, _, bank = account.strip().partition("/")
    prefix, _, number = local.rpartition("-")
    if (
        not bank.isdigit()
        or len(bank) != 4
        or not number.isdigit()
        or (prefix and not prefix.isdigit())
    ):
        raise ValueError(f"not a Czech domestic account: {account!r}")
    return _iban_from_bban(bank + prefix.zfill(6) + number.zfill(10))


# ---------------------------------------------------------------------------
# Phone number
# ---------------------------------------------------------------------------


_CZ_MOBILE_PREFIXES = (
    "601",
    "602",
    "603",
    "604",
    "605",
    "606",
    "607",
    "608",
    "702",
    "703",
    "704",
    "720",
    "721",
    "722",
    "723",
    "724",
    "725",
    "726",
    "727",
    "728",
    "729",
    "730",
    "731",
    "732",
    "733",
    "734",
    "735",
    "736",
    "737",
    "738",
    "739",
    "770",
    "771",
    "772",
    "773",
    "774",
    "775",
    "776",
    "777",
    "778",
    "779",
    "790",
    "791",
    "792",
    "793",
    "794",
    "795",
    "796",
    "797",
    "798",
    "799",
)


def generate_phone(rng: Random) -> str:
    """Return a Czech mobile phone number in '+420 NNN NNN NNN' format."""
    prefix = rng.choice(_CZ_MOBILE_PREFIXES)
    tail = "".join(str(rng.randint(0, 9)) for _ in range(6))
    digits = prefix + tail  # 9 digits total
    return "+420 " + digits[:3] + " " + digits[3:6] + " " + digits[6:]


# ---------------------------------------------------------------------------
# Rodné číslo
# ---------------------------------------------------------------------------


def generate_rc(
    year: int,
    month: int,
    sex: str,
    rng: Random,
) -> str:
    """Generate a checksum-valid fictional Czech rodné číslo.

    Args:
        year:  Full birth year (e.g. 1985).
        month: Birth month 1-12.
        sex:   'f' for female (month field += 50), any other value for male.
        rng:   Seeded random instance.

    Returns:
        RC in 'YYMMDD/XXXX' format where the 10 digits are divisible by 11.
    """
    yy = year % 100
    mm = month + (50 if sex == "f" else 0)
    max_day = _days_in_month(year, month)

    while True:
        dd = rng.randint(1, max_day)
        serial = rng.randint(0, 999)
        # Build the first 9 digits
        prefix = str(yy).zfill(2) + str(mm).zfill(2) + str(dd).zfill(2) + str(serial).zfill(3)
        # Find check digit 0-9 such that the 10-digit integer % 11 == 0
        for check in range(10):
            full = prefix + str(check)
            if int(full) % 11 == 0:
                return prefix[:6] + "/" + prefix[6:] + str(check)
        # No valid check digit found for this (dd, serial) — retry


# ---------------------------------------------------------------------------
# Bank account
# ---------------------------------------------------------------------------


def generate_bank_account(rng: Random) -> str:
    """Return a Czech domestic bank account in '[predcisli-]cislo/kod' format.

    - Optional prefix: 0 to 6 digits (omitted ~50 % of the time).
    - Account number: 2 to 10 digits.
    - Bank code: 4 digits chosen from the IBAN bank-code set.
    """
    bank = rng.choice(_IBAN_BANK_CODES)

    account_len = rng.randint(2, 10)
    account = str(rng.randint(10 ** (account_len - 1), 10**account_len - 1))

    if rng.random() < 0.5:
        prefix_len = rng.randint(1, 6)
        prefix = str(rng.randint(0, 10**prefix_len - 1)).zfill(prefix_len)
        return f"{prefix}-{account}/{bank}"
    return f"{account}/{bank}"


# ---------------------------------------------------------------------------
# PSČ
# ---------------------------------------------------------------------------


def generate_psc(rng: Random) -> str:
    """Return a fictional Czech PSČ in 'NNN NN' format.

    First digit is 1-7 (valid Czech postal districts).
    """
    first = rng.randint(1, 7)
    rest = rng.randint(0, 9999)
    digits = str(first) + str(rest).zfill(4)
    return digits[:3] + " " + digits[3:]


__all__ = [
    "generate_ico",
    "generate_dic",
    "generate_iban_cz",
    "iban_from_bank_account",
    "generate_phone",
    "generate_rc",
    "generate_bank_account",
    "generate_psc",
]
