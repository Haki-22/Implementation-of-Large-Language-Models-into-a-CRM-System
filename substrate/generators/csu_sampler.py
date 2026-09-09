"""Seeded sampler over official Czech demographic distributions.

Draws synthetic-but-realistic ages, sexes and municipalities from two reduced
tables of ČSÚ open data (CC BY 4.0), produced and documented by
``substrate/pipeline/data_acquisition/fetch_csu.py``:

  - ``substrate/data/cz_age_sex.csv``        -- population of Czechia by sex and single year of age
  - ``substrate/data/cz_municipalities.csv`` -- every municipality with population, district, region
                                      and the postal codes of its parts (Czech Post list)

Both files start with ``#`` provenance lines (source set, URL, reference date,
download date, raw md5, licence) that are skipped on parse. The parsed data is
cached at module level so the CSVs are read only once.

All sampling is driven by an explicit ``random.Random`` instance, so callers
get fully deterministic output for a fixed seed.
"""

from __future__ import annotations

import calendar
import csv
import datetime
import random
from pathlib import Path

from substrate.constants import SUBSTRATE_REFERENCE_DATE
from utils.paths import SUBSTRATE_DATA_DIR as _DATA_DIR

_AGE_SEX_CSV = _DATA_DIR / "cz_age_sex.csv"
_MUNICIPALITIES_CSV = _DATA_DIR / "cz_municipalities.csv"

# Module-level caches, populated lazily on first use.
_age_sex_rows: list[dict[str, object]] | None = None
_municipality_rows: list[dict[str, object]] | None = None


# ---------------------------------------------------------------------------
# Table loading
# ---------------------------------------------------------------------------


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV file, skipping the leading ``#`` provenance comment lines."""
    with path.open(encoding="utf-8", newline="") as fh:
        lines = [line for line in fh if not line.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    return [row for row in reader]


def _load_age_sex() -> list[dict[str, object]]:
    """Return the cached ``(age, sex, count)`` table from ``cz_age_sex.csv``."""
    global _age_sex_rows
    if _age_sex_rows is None:
        _age_sex_rows = [
            {
                "age": int(row["age"]),
                "sex": row["sex"].strip(),
                "count": int(row["count"]),
            }
            for row in _read_csv_rows(_AGE_SEX_CSV)
        ]
    return _age_sex_rows


def _load_municipalities() -> list[dict[str, object]]:
    """Return the cached municipality table from ``cz_municipalities.csv``."""
    global _municipality_rows
    if _municipality_rows is None:
        _municipality_rows = [
            {
                "code": row["code"].strip(),
                "city": row["city"].strip(),
                "district": row["district"].strip(),
                "region": row["region"].strip(),
                "population": int(row["population"]),
                "postal_codes": sorted(code for code in row["postal_codes"].split("|") if code),
            }
            for row in _read_csv_rows(_MUNICIPALITIES_CSV)
        ]
    return _municipality_rows


# ---------------------------------------------------------------------------
# Age and sex
# ---------------------------------------------------------------------------


def sample_age_sex(
    rng: random.Random,
    min_age: int = 18,
    max_age: int = 90,
) -> tuple[int, str]:
    """Draw an (age, sex) pair jointly from the Czech adult population.

    Both dimensions of the ČSÚ table are used: the pair is sampled from the
    joint age x sex distribution, so a contact's sex carries the real population
    ratio at its age rather than a coin flip.

    Args:
        rng: Seeded ``random.Random`` instance driving the draw.
        min_age: Minimum age (inclusive) at ``SUBSTRATE_REFERENCE_DATE``.
        max_age: Maximum age (inclusive) at ``SUBSTRATE_REFERENCE_DATE``.

    Returns:
        ``(age, sex)`` with sex in ``{"m", "f"}``.

    Raises:
        ValueError: If ``min_age > max_age`` or the range holds no population.
    """
    if min_age > max_age:
        raise ValueError(f"min_age ({min_age}) must not exceed max_age ({max_age})")

    rows = [row for row in _load_age_sex() if min_age <= int(row["age"]) <= max_age]
    if not rows:
        raise ValueError(f"no population available in range [{min_age}, {max_age}]")

    row = rng.choices(rows, weights=[int(r["count"]) for r in rows], k=1)[0]
    return int(row["age"]), str(row["sex"])


def sample_age(
    rng: random.Random,
    sex: str | None = None,
    min_age: int = 18,
    max_age: int = 90,
) -> int:
    """Draw an age, optionally conditioned on a sex that is already fixed.

    Used where the sex comes from somewhere else than the population table --
    a foreign-origin contact carries the sex of its name entry, and a defective
    contact may have had its sex nulled on purpose.

    Args:
        rng: Seeded ``random.Random`` instance driving the draw.
        sex: ``"m"`` / ``"f"`` to condition on, or None for the age marginal.
        min_age: Minimum age (inclusive) at ``SUBSTRATE_REFERENCE_DATE``.
        max_age: Maximum age (inclusive) at ``SUBSTRATE_REFERENCE_DATE``.

    Returns:
        An age in ``[min_age, max_age]``.

    Raises:
        ValueError: If ``min_age > max_age`` or the selection holds no population.
    """
    if min_age > max_age:
        raise ValueError(f"min_age ({min_age}) must not exceed max_age ({max_age})")

    rows = [
        row
        for row in _load_age_sex()
        if min_age <= int(row["age"]) <= max_age and (sex is None or row["sex"] == sex)
    ]
    if not rows:
        raise ValueError(f"no population available in range [{min_age}, {max_age}] for sex={sex!r}")

    weights: dict[int, int] = {}
    for row in rows:
        weights[int(row["age"])] = weights.get(int(row["age"]), 0) + int(row["count"])
    ages = list(weights)
    return rng.choices(ages, weights=[weights[a] for a in ages], k=1)[0]


def birth_date_for_age(
    rng: random.Random,
    age: int,
    ref_year: int = SUBSTRATE_REFERENCE_DATE.year,
) -> datetime.date:
    """Turn an age into a birth date by drawing a uniform day in the birth year.

    Ages are measured at ``SUBSTRATE_REFERENCE_DATE`` (the substrate's "today",
    the day of the last Amazon order), so a contact's age agrees with the
    behavioural timeline rather than with the wall clock.

    Args:
        rng: Seeded ``random.Random`` instance driving the day-of-year draw.
        age: Age at ``ref_year``.
        ref_year: Reference year against which the age is measured.

    Returns:
        A ``datetime.date`` whose implied age at ``ref_year`` is ``age``.
    """
    birth_year = ref_year - age
    days_in_year = 366 if calendar.isleap(birth_year) else 365
    day_of_year = rng.randint(1, days_in_year)
    return datetime.date(birth_year, 1, 1) + datetime.timedelta(days=day_of_year - 1)


# ---------------------------------------------------------------------------
# Municipality
# ---------------------------------------------------------------------------


def sample_municipality(rng: random.Random) -> dict[str, str]:
    """Sample a Czech municipality weighted by population, and one of its postal codes.

    Args:
        rng: Seeded ``random.Random`` instance driving the draws.

    Returns:
        A dict with keys ``city``, ``district``, ``region`` and ``postal_code``
        (one of the municipality's postal codes, drawn uniformly). All four are
        persisted on the contact.
    """
    rows = _load_municipalities()
    weights = [int(row["population"]) for row in rows]
    row = rng.choices(rows, weights=weights, k=1)[0]
    return {
        "city": str(row["city"]),
        "district": str(row["district"]),
        "region": str(row["region"]),
        "postal_code": rng.choice(list(row["postal_codes"])),
    }
