"""Tests for the ČSÚ age/sex + municipality sampler and the provenance of its tables."""

import random
import re

from substrate.constants import SUBSTRATE_REFERENCE_DATE
from substrate.generators import csu_sampler
from substrate.generators.csu_sampler import (
    birth_date_for_age,
    sample_age,
    sample_age_sex,
    sample_municipality,
)


def test_sample_age_sex_stays_in_the_adult_range():
    rng = random.Random(1)
    for _ in range(50):
        age, sex = sample_age_sex(rng, min_age=18, max_age=80)
        assert 18 <= age <= 80
        assert sex in ("m", "f")


def test_sample_age_sex_reproduces_the_population_sex_ratio():
    """Both dimensions of the table are used, so the draw is not a 50/50 coin."""
    rows = [r for r in csu_sampler._load_age_sex() if 18 <= int(r["age"]) <= 90]
    total = sum(int(r["count"]) for r in rows)
    expected_female = sum(int(r["count"]) for r in rows if r["sex"] == "f") / total

    rng = random.Random(11)
    draws = [sample_age_sex(rng) for _ in range(4000)]
    observed_female = sum(1 for _, sex in draws if sex == "f") / len(draws)

    assert abs(observed_female - expected_female) < 0.03


def test_sample_age_conditions_on_a_given_sex():
    """Women live longer, so the conditional mean age is higher for f than for m."""
    rng = random.Random(3)
    mean_f = sum(sample_age(rng, sex="f") for _ in range(2000)) / 2000
    mean_m = sum(sample_age(rng, sex="m") for _ in range(2000)) / 2000
    assert mean_f > mean_m


def test_birth_date_for_age_measures_age_at_the_substrate_reference_date():
    rng = random.Random(4)
    for age in (18, 45, 90):
        dob = birth_date_for_age(rng, age)
        assert SUBSTRATE_REFERENCE_DATE.year - dob.year == age


def test_sample_municipality_returns_city_district_region_psc():
    rng = random.Random(2)
    m = sample_municipality(rng)
    assert m["city"] and m["district"] and m["region"]
    assert re.fullmatch(r"\d{5}", m["postal_code"])


def test_sample_municipality_deterministic():
    assert sample_municipality(random.Random(7)) == sample_municipality(random.Random(7))


def test_tables_are_real_csu_reductions_with_provenance():
    """Both CSVs carry the provenance header and the full ČSÚ tables, not a hand-made approximation."""
    for path in (csu_sampler._AGE_SEX_CSV, csu_sampler._MUNICIPALITIES_CSV):
        head = path.read_text(encoding="utf-8").splitlines()[:8]
        assert any(line.startswith("# Source: Český statistický úřad") for line in head), path.name
        assert any("raw md5" in line for line in head), path.name
        assert any("CC BY 4.0" in line for line in head), path.name

    ages = csu_sampler._load_age_sex()
    assert len(ages) == 202 and {r["sex"] for r in ages} == {"m", "f"}
    assert {r["age"] for r in ages} == set(range(0, 101))
    for sex in ("m", "f"):
        assert sum(r["count"] for r in ages if r["sex"] == sex) > 5_000_000

    towns = csu_sampler._load_municipalities()
    assert len(towns) > 6000
    praha = next(t for t in towns if t["city"] == "Praha")
    assert praha["population"] > 1_300_000 and len(praha["postal_codes"]) > 30
    assert praha["region"] == "Hlavní město Praha"
    assert all(t["population"] > 0 and t["postal_codes"] for t in towns)
