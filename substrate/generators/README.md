# `substrate/generators/` — synthetic-data library

Seeded, deterministic generators for the substrate. Imported as
`substrate.generators.*`, and run as `python -m substrate.generators` —
`__main__.py` is the package's only entry point, so there is exactly one path
from a generator to a committed artifact. No I/O on import, no network calls, no LLM
calls at module scope.

## Structure

| Module | What it produces |
| --- | --- |
| `contacts/` | 500 fictional Czech customer / B2B contacts. Age + sex drawn jointly from the ČSÚ age x sex table, then a matching Faker name, vocative greeting (via `vokativ`), formality, OCEAN personality (BFI-2 norms modulated by the two persisted CRMArena latents), PII overlay (e-mail / phone / address incl. district + region / date of birth / bank account / IBAN). No free text: the Czech `prior_interactions` / `frequent_words` / `style_excerpt` come from the translated reviews at assembly time. The runner (`__main__.py`) then pairs the first 425 contacts with the stratified reviewers inside each group so genders match wherever the reviewer's gender is known (`snapshots/amazon/reviewer-gender.json`), recording `reviewer_gender` + `gender_paired`. See `contacts/__init__.py` for the full recipe. |
| `companies.py` | The retailer's B2B partners. Default = the hand-written pool of 8 partner names (`PARTNER_COMPANY_NAMES`, the same pool the contact generator affiliates contacts with), each given mod-11-valid IČO, DIČ, the same ČSÚ address draw a contact gets (city + postal code + district + region) in the same street format, and the legal form read from its name suffix. `generate_companies(n=...)` produces Faker-named companies instead of the partner pool. |
| `notes/` | 80 seeded Czech CRM notes (the salesperson's records UC-03 reads and appends to). Czech templates with gender-agreeing verbs, categories shared with UC-03's categoriser, about 30 % embedding one of the contact's own PII fields (never invented), uneven distribution (small hot set, warm tail, cold long tail), timestamps from the fixed `NOTES_ANCHOR`. |
| `csu_sampler.py` | Weighted samplers over official Czech demographic distributions: age / sex from `data/cz_age_sex.csv` (ČSÚ OBY02B, Czechia by single year of age, 1. 1. 2025), municipality + district + region + postal code from `data/cz_municipalities.csv` (ČSÚ OBY02A, all 6 254 municipalities with population, 1. 1. 2026, postal codes from the Czech Post list). `sample_age_sex` draws the pair jointly, so the cohort carries the real population sex ratio rather than a coin flip; `sample_age(sex=...)` conditions on an already-fixed sex, and `birth_date_for_age` turns an age into a date. Ages are measured at the substrate reference date. |
| `../data/` | The two reduced ČSÚ tables (CC BY 4.0) with provenance headers, read by `csu_sampler.py`; produced by `python -m substrate.pipeline.data_acquisition.fetch_csu`. Since 2026-09-04 all committed inputs live in `substrate/data/` (see its README); the raw downloads stay under `pipeline/data_acquisition/downloaded/`, git-ignored and pinned by md5. |

### Modules inside the two packages

Private modules, imported only by their package's `__init__.py` (the recipe) or the runner; named here so every file has a line.

| Module | Does |
| --- | --- |
| `contacts/_constants.py` | Module-level constants of the contact generator (counts, splits, formality odds, seeds). |
| `contacts/_factory.py` | The contact factory functions: one deterministic contact from the drawn age, sex, name. |
| `contacts/_vocative.py` | Czech vocative greeting builder (`vokativ`), the stored `name_vocative`. |
| `contacts/_pii.py` | PII overlay: e-mail, phone, address with district and region, date of birth, bank account, IBAN (checksummed). |
| `contacts/_ocean.py` | OCEAN trait sampling from BFI-2 norms, modulated by the two persisted CRMArena latents. |
| `contacts/_snapshot.py` | JSON snapshot persistence for the generated contacts. |
| `notes/_distribution.py` | Decides which contacts get notes and how many (hot set, warm tail, cold long tail). |
| `notes/_templates.py` | The Czech text the seeded notes are rendered from, per category, with gender-agreeing verbs. |
| `notes/_render.py` | Turns one template and one contact row into a note (fills the contact's own PII field). |
| `notes/_factory.py` | Assembles the note rows from the distribution, the templates and the render step. |
| `notes/_snapshot.py` | Writes the committed note snapshot. |

## How to use

Run from the repository root after the [main setup](../../README.md#quickstart). OCEAN denotes the five Big Five personality traits; BFI-2 is the inventory whose population norms inform the synthetic draw. These are generated profiles, not assessments of real customers.

```python
import random
from substrate.generators import contacts, companies, notes
from utils import czech_identifiers

# Generate a deterministic batch of Czech contacts.
# Every count is explicit: the substrate's own numbers (500, a 90/10 split,
# 2 foreign, seed 42) live in the runner `__main__.py`, not in the function.
contact_rows = contacts.generate_contacts(
    seed=42,
    n_clean=10,
    n_non_clean=0,
    n_foreign=0,
)

# Generate one mod-11-valid IČO for unit tests.
rng = random.Random(42)
ico = czech_identifiers.generate_ico(rng)
assert czech_identifiers.is_valid_ico(ico)
```

Every public generator either accepts a `random.Random` instance or a
`seed` integer. Repeatability also depends on unchanged inputs and dependency versions. Do not
introduce module-level state that depends on wall-clock time, the
process RNG, or environment variables; the substrate's reproducibility
guarantee relies on this.

Most code should read the committed `substrate.db` rather than call these
generators directly. Call into this package only when:

- producing a new snapshot (you ran out of an existing one and need a
  different seed or contact count);
- writing a test that needs an inline tiny synthetic batch (use a
  fresh `random.Random(seed)` and a `tmp_path`);
- generating a Czech identifier — that lives in `utils/czech_identifiers/`
  (patterns / validate / generate), since UC-02's pseudonymiser validates
  against it at run time.

## Outputs

Every module here is import-only; importing writes nothing. Running the package with `--force` replaces the corresponding snapshots and,
unless `--snapshots-only` is selected, the database. Use a separate copy to retain
existing inputs and local CRM edits:

```bash
python -m substrate.generators --force                   # snapshots -> DB
python -m substrate.generators --force --snapshots-only  # stop at the snapshots
```

- `../snapshots/contacts/` — the three identity snapshots, written together
  under one seed so they cannot describe different cohorts.
- `../snapshots/ocean/ocean_synthetic_500.json` — the OCEAN projection, refreshed
  because it is derived from the contacts.
- `../snapshots/substrate.db` — reassembled by `../pipeline/build_substrate_db.py`.

`../pipeline/build_all.py` calls the `--snapshots-only` form and runs the
projection and the database as steps of its own, so it can report each one.

## Next step

- `../README.md` — substrate overview and the full build chain.
- `../pipeline/README.md` — scripts that call these generators to produce
  the committed snapshots.
- `../schema/README.md` — SQLModel entities the generated rows map onto.
