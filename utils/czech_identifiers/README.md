# `utils/czech_identifiers/` — Czech identifier formats

Everything the prototype knows about the shape of a Czech IČO, DIČ, rodné číslo,
IBAN, bank account, phone number and PSČ: how to **spot** one, how to **check**
one, and how to **build** a fictional one.

Pure functions. No I/O, no network, no LLM, no database. Generated values are for synthetic examples. Passing a format or checksum
does not prove that a value is unassigned in a real registry; no registry is queried.

## Three parts, because three callers need different halves

| Module | Holds | Used by |
| --- | --- | --- |
| `patterns.py` | `REGEX` — surface-form recognizers. Shape only, never validity. | UC-02 `pseudonymizer.py`, UC-02 `ner_presidio.py` |
| `validate.py` | `ico_check_digit`, `is_valid_ico`, `is_valid_iban_cz`, `is_valid_rc`, `days_in_month` | UC-02 `pseudonymizer.py` (**per message**), UC-02 `pii_corpus.py` |
| `generate.py` | `generate_ico` / `_dic` / `_iban_cz` / `_phone` / `_rc` / `_bank_account` / `_psc`, all seeded | substrate `companies.py` + `contacts/_pii.py`, UC-02 `pii_corpus.py` |

The split is the workflow: **detect** with `patterns`, **confirm** with
`validate`, **synthesise** with `generate`. And because `generate` builds against
the very rules `validate` checks, a generated identifier passes its own
validator by construction — the round trip is a test, not a coincidence.

## Why UC-02 cares about the middle column

`REGEX["ICO"]` is `\b\d{8}\b` — it matches every eight-digit number in a Czech
sentence, invoice numbers and order ids included. `pseudonymizer.py` tags a span
as `ICO` only when `ico_check_digit` agrees, and the same holds for `RC`
(mod-11) and `IBAN` (ISO 7064 mod-97-10). The checksum gate reduces accidental matches but does not prove identity, and it runs
on every message the use case pseudonymises.

## What `is_valid_rc` actually enforces

The rodné číslo is the fiddliest of the formats, and a validator that is too
strict silently drops real identifiers — a privacy failure in UC-02, not a
cosmetic bug. It accepts:

- Month bands 01–12, 51–62, 21–32 and 71–82.
- The modulo-11 check, including the legacy remainder-10/check-digit-0 exception.
- A nine-digit short form with day-range checks rather than an assumed century.

These are implementation rules, not a registry check or a complete legal validity determination.

Each rule has a named regression test in `tests/utils/test_czech_identifiers.py`.

## Importing

Both work; pick whichever reads better where you are:

```python
from utils.czech_identifiers import generate_ico, is_valid_rc, REGEX  # flat surface
from utils.czech_identifiers.validate import is_valid_rc              # by part
```

Runtime call sites import **by part**, so a reader can see at a glance which
half a module depends on. The flat surface in `__init__.py` re-exports every
public name for convenience.

## Determinism

Every generator takes an explicit `random.Random`; no global RNG, no wall clock.
Same seed, same identifier — which is what lets the substrate snapshots and the
UC-02 corpus be regenerated with fixed inputs and compatible dependencies.

## Why this is shared

The substrate needs generators, while UC-02 needs patterns and validators at
runtime. Keeping the three parts here avoids importing synthetic-data generation
code just to pseudonymise a message. See the [utils guide](../README.md) for
shared-library boundaries.
