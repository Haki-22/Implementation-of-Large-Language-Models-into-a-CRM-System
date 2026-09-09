"""Download and reduce the Czech open data behind ``substrate/generators/csu_sampler.py``.

Two committed tables drive the demographic draws of the synthetic contacts:

- ``substrate/data/cz_age_sex.csv``: population of Czechia by sex and single
  year of age (0 … 100+), the weights behind ``sample_age_sex`` / ``sample_age``.
- ``substrate/data/cz_municipalities.csv``: every Czech municipality with its
  population (the weight behind ``sample_municipality``), district, region and the postal
  codes of its parts.

Sources (all public, downloaded by ``--download`` into ``downloaded/csu/``, never committed):

- ČSÚ open data set ``OBY02B`` "Počet obyvatel podle pohlaví a jednotek věku"
  (product 132000 "Obyvatelstvo - stav a věková struktura"), CSV distribution
  ``https://data.csu.gov.cz/opendata/sady/OBY02B/distribuce/csv``. Rows used: territory
  ``CZ``, indicator ``2406P`` "Počet obyvatel k 1. 1. (počáteční stav)", sexes ``1``/``2``,
  the latest year that carries single-year ages.
- ČSÚ open data set ``OBY02A`` "Počet obyvatel podle pohlaví" by territory down to
  municipalities, CSV ``https://data.csu.gov.cz/opendata/sady/OBY02A/distribuce/csv``.
  Rows used: six-digit municipality codes, indicator ``2406P``, both sexes together, the
  latest year. District and region come from the same file (LAU1 / NUTS3 rows).
- Česká pošta "Seznam PSČ částí obcí a obcí bez částí" (``zv_pcobc.csv`` inside
  ``https://www.ceskaposta.cz/documents/d/guest/db_pcobc-zip?download=true``, listed at
  ``https://www.ceskaposta.cz/cs/ke-stazeni/zakaznicke-vystupy``), joined on
  (municipality, district) to attach the postal codes of a municipality's parts.

Licence: ČSÚ data are released under CC BY 4.0 (attribution "Zdroj: ČSÚ",
``https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu``);
the derived tables here are reductions, not official ČSÚ statistics. The Czech Post list is
a public customer output used only for the postal-code join.

The ČSÚ sets are refreshed yearly, so the raw files are pinned by size and md5 as
downloaded on the date recorded below; ``--verify-only`` reports drift, the reduction
writes the actual md5 into the CSV headers either way.

Run:
    python -m substrate.pipeline.data_acquisition.fetch_csu --download    # ~900 MB into downloaded/csu/
    python -m substrate.pipeline.data_acquisition.fetch_csu --verify-only
    python -m substrate.pipeline.data_acquisition.fetch_csu --force       # rewrite the two CSVs
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from substrate.pipeline.data_acquisition import _pinned
from utils.file_safety import file_md5, require_can_write
from utils.paths import DOWNLOADS_DIR, SUBSTRATE_DATA_DIR

RAW_DIR = DOWNLOADS_DIR / "csu"
DATA_DIR = SUBSTRATE_DATA_DIR
AGE_SEX_CSV = DATA_DIR / "cz_age_sex.csv"
MUNICIPALITIES_CSV = DATA_DIR / "cz_municipalities.csv"

PINNED_ON = date(2026, 9, 2)
SOURCES: dict[str, dict] = {
    "OBY02B.csv": {
        "url": "https://data.csu.gov.cz/opendata/sady/OBY02B/distribuce/csv",
        "doc": "https://data.csu.gov.cz/datastat/info/SADA/OBY02B",
        "size": 689086805,
        "md5": "45e7a9220826f581989a66818216d44f",
    },
    "OBY02A.csv": {
        "url": "https://data.csu.gov.cz/opendata/sady/OBY02A/distribuce/csv",
        "doc": "https://data.csu.gov.cz/datastat/info/SADA/OBY02A",
        "size": 195437903,
        "md5": "b78bf3127fdede5d4090fabfbdddfa21",
    },
    "psc_obce.zip": {
        "url": "https://www.ceskaposta.cz/documents/d/guest/db_pcobc-zip?download=true",
        "doc": "https://www.ceskaposta.cz/cs/ke-stazeni/zakaznicke-vystupy",
        "size": 213918,
        "md5": "faca019178260cb9abe24d4741381855",
    },
}

_INDICATOR_START_OF_YEAR = "2406P"  # "Počet obyvatel k 1. 1. (počáteční stav)"
_MUNICIPALITY_CODE = re.compile(r"\d{6}")
_DISTRICT_CODE = re.compile(r"CZ\d{3}[0-9A-C]")  # LAU1
_REGION_CODE = re.compile(r"CZ\d{3}")  # NUTS3
_LABEL = re.compile(r"(.+?) \(okr\. (.+)\)")


# ---------------------------------------------------------------------------
# Pinned sources
# ---------------------------------------------------------------------------


def verify(raw_dir: Path = RAW_DIR) -> dict[str, str]:
    """Return per-file status against the pins in ``SOURCES``."""
    return _pinned.verify(SOURCES, raw_dir)


def download(raw_dir: Path = RAW_DIR, *, force: bool = False) -> dict[str, str]:
    """Fetch whatever is missing from ``SOURCES``; return the verify status."""
    return _pinned.download(SOURCES, raw_dir, force=force)


# ---------------------------------------------------------------------------
# Reductions
# ---------------------------------------------------------------------------


def reduce_age_sex(raw_b: Path) -> tuple[str, list[dict]]:
    """Return (reference year, rows age/sex/count) for Czechia, single years of age."""
    by_year: dict[str, list[dict]] = defaultdict(list)
    with raw_b.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["UZ01234B"] != "CZ" or row["IndicatorType"] != _INDICATOR_START_OF_YEAR:
                continue
            if row["POHL2"] not in ("1", "2") or row["VEK1C"] == "VEKC":
                continue
            by_year[row["CasRB"]].append(row)
    years = sorted(y for y, rows in by_year.items() if len(rows) >= 200)
    if not years:
        raise RuntimeError("OBY02B: no year with single-year ages for territory CZ")
    year = years[-1]
    out = []
    for row in by_year[year]:
        label = row["Věk (roky)"]
        age = int(label.split()[0])  # "100 a více" -> 100
        out.append(
            {"age": age, "sex": "m" if row["POHL2"] == "1" else "f", "count": int(row["Hodnota"])}
        )
    out.sort(key=lambda r: (r["age"], r["sex"]))
    if len(out) != 202:
        raise RuntimeError(f"OBY02B {year}: expected 202 age x sex rows, got {len(out)}")
    return year, out


def _load_postal_codes(raw_zip: Path) -> dict[tuple[str, str], set[str]]:
    """(municipality, district) -> postal codes of its parts, from the Czech Post list."""
    with zipfile.ZipFile(raw_zip) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = zf.read(name).decode("cp1250")
    codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        codes[(row["NAZOBCE"], row["NAZOKRESU"])].add(row["PSC"])
    return codes


def reduce_municipalities(raw_a: Path, raw_zip: Path) -> tuple[str, list[dict], dict]:
    """Return (reference year, rows, stats) for every municipality with population > 0."""
    municipalities: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    districts: dict[str, str] = {}
    regions: dict[str, str] = {}
    with raw_a.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["POHL2"] != "0" or row["IndicatorType"] != _INDICATOR_START_OF_YEAR:
                continue
            code, label = row["UZ01234596C"], row["Všechna území"]
            if _MUNICIPALITY_CODE.fullmatch(code):
                municipalities[row["CasR"]].append((code, label, int(row["Hodnota"])))
            elif _DISTRICT_CODE.fullmatch(code):
                districts[label] = code
            elif _REGION_CODE.fullmatch(code):
                regions[code] = label
    year = max(municipalities)
    postal = _load_postal_codes(raw_zip)

    rows: list[dict] = []
    stats = {"municipalities": 0, "skipped_zero_population": 0, "unmatched_postal": []}
    for code, label, population in sorted(municipalities[year]):
        m = _LABEL.fullmatch(label)
        if not m:
            raise RuntimeError(f"OBY02A: unexpected municipality label {label!r}")
        city, district = m.group(1), m.group(2)
        district_code = districts.get(district)
        if district_code is None:
            # Prague: the municipality label says "(okr. Praha)" while the LAU1 row is
            # named after the region ("Hlavní město Praha"); resolve through the region names.
            district_code = next(
                (
                    code
                    for code, name in regions.items()
                    if name.endswith(district) or district in name
                ),
                None,
            )
        region = regions.get(district_code[:5]) if district_code else None
        if region is None:
            raise RuntimeError(f"OBY02A: no region for district {district!r} of {city!r}")
        if population <= 0:
            stats["skipped_zero_population"] += 1  # military training areas
            continue
        # Czech Post names Prague's district by the region ("Hlavní město Praha").
        codes = postal.get((city, district)) or postal.get((city, region))
        if not codes:
            stats["unmatched_postal"].append(label)
            continue
        rows.append(
            {
                "code": code,
                "city": city,
                "district": district,
                "region": region,
                "population": population,
                "postal_codes": "|".join(sorted(codes)),
            }
        )
    stats["municipalities"] = len(rows)
    return year, rows, stats


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _header(lines: list[str]) -> str:
    """Join `lines` into a `#`-prefixed provenance comment block for a CSV file."""
    return "".join(f"# {line}\n" for line in lines)


def write_age_sex(path: Path, year: str, rows: list[dict], raw_b: Path, *, force: bool) -> None:
    """Write cz_age_sex.csv with its provenance header."""
    require_can_write(path, overwrite=force, artifact="age/sex table")
    spec = SOURCES["OBY02B.csv"]
    head = _header(
        [
            "Source: Český statistický úřad (ČSÚ), open data set OBY02B 'Počet obyvatel podle pohlaví a jednotek věku'",
            f"URL: {spec['url']} (documentation {spec['doc']})",
            f"Rows used: territory CZ, indicator {_INDICATOR_START_OF_YEAR} 'Počet obyvatel k 1. 1.', reference 1. 1. {year}",
            f"Downloaded: {PINNED_ON.isoformat()}, raw md5 {file_md5(raw_b)}; reduced by substrate/pipeline/data_acquisition/fetch_csu.py",
            "Licence: CC BY 4.0, Zdroj: ČSÚ (https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu); derived table, not official ČSÚ statistics",
            "age 100 = '100 a více'; count = persons",
        ]
    )
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(head)
        w = csv.DictWriter(fh, fieldnames=["age", "sex", "count"])
        w.writeheader()
        w.writerows(rows)


def write_municipalities(
    path: Path, year: str, rows: list[dict], stats: dict, raw_a: Path, raw_zip: Path, *, force: bool
) -> None:
    """Write cz_municipalities.csv with its provenance header."""
    require_can_write(path, overwrite=force, artifact="municipality table")
    spec_a, spec_p = SOURCES["OBY02A.csv"], SOURCES["psc_obce.zip"]
    head = _header(
        [
            "Source: Český statistický úřad (ČSÚ), open data set OBY02A 'Počet obyvatel podle pohlaví' (municipalities) + Česká pošta 'Seznam PSČ částí obcí a obcí bez částí'",
            f"URL: {spec_a['url']} (documentation {spec_a['doc']}); postal codes {spec_p['url']} ({spec_p['doc']})",
            f"Rows used: six-digit municipality codes, indicator {_INDICATOR_START_OF_YEAR} 'Počet obyvatel k 1. 1.', both sexes, reference 1. 1. {year}; district/region from the LAU1/NUTS3 rows of the same set",
            f"Downloaded: {PINNED_ON.isoformat()}, raw md5 OBY02A {file_md5(raw_a)}, postal list {file_md5(raw_zip)}; reduced by substrate/pipeline/data_acquisition/fetch_csu.py",
            f"Kept {stats['municipalities']} municipalities with population > 0; skipped {stats['skipped_zero_population']} with 0 (military areas); {len(stats['unmatched_postal'])} without a postal-code match: {', '.join(stats['unmatched_postal']) or 'none'}",
            "Licence: CC BY 4.0, Zdroj: ČSÚ (https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu); derived table, not official ČSÚ statistics. Postal codes: public Czech Post customer output.",
            "postal_codes = all postal codes of the municipality's parts, '|'-separated",
        ]
    )
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(head)
        w = csv.DictWriter(
            fh, fieldnames=["code", "city", "district", "region", "population", "postal_codes"]
        )
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: download, verify, or reduce the ČSÚ and Czech Post sources into the two CSVs."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="fetch missing raw files into downloaded/csu/, then verify",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check downloaded/csu/ against the pinned sizes and md5s",
    )
    parser.add_argument("--force", action="store_true", help="rewrite the two committed CSVs")
    args = parser.parse_args(argv)

    if args.download:
        status = download(RAW_DIR)
        print("\n".join(f"{k}: {v}" for k, v in status.items()))
        return 0
    status = verify(RAW_DIR)
    if args.verify_only:
        print("\n".join(f"{k}: {v}" for k, v in status.items()))
        return 0 if all(v == "ok" for v in status.values()) else 1
    missing = [k for k, v in status.items() if v == "missing"]
    if missing:
        print(f"raw files missing: {missing}. Run with --download first.", file=sys.stderr)
        return 1
    drift = {k: v for k, v in status.items() if v != "ok"}
    if drift:
        print(
            f"note: raw files differ from the pinned versions ({drift}); the headers record the actual md5."
        )

    year_b, age_rows = reduce_age_sex(RAW_DIR / "OBY02B.csv")
    year_a, mun_rows, stats = reduce_municipalities(
        RAW_DIR / "OBY02A.csv", RAW_DIR / "psc_obce.zip"
    )
    write_age_sex(AGE_SEX_CSV, year_b, age_rows, RAW_DIR / "OBY02B.csv", force=args.force)
    write_municipalities(
        MUNICIPALITIES_CSV,
        year_a,
        mun_rows,
        stats,
        RAW_DIR / "OBY02A.csv",
        RAW_DIR / "psc_obce.zip",
        force=args.force,
    )
    print(f"wrote {AGE_SEX_CSV.name}: {len(age_rows)} rows, reference 1. 1. {year_b}")
    print(
        f"wrote {MUNICIPALITIES_CSV.name}: {stats['municipalities']} municipalities, reference 1. 1. {year_a}, "
        f"skipped {stats['skipped_zero_population']} empty, unmatched postal {stats['unmatched_postal']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
