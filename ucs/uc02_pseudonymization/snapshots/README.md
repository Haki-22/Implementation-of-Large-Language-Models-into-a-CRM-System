# `uc02_pseudonymization/snapshots/` — the corpus of record and its backup

The planted-PII corpus is the exam paper of UC-02: Czech CRM texts in which the
generator knows exactly which characters are personal data, because it planted
them from the CRM rows (`uc_contacts` + `uc_companies` in `substrate.db`). Nothing is trained on it; the detector is scored against it.

## Files

Paths are relative to this folder; producer commands run from the repository root. They replace these inputs with `--force`, so they are not installation steps. Read the [UC-02 guide](../README.md) before rebuilding the corpus.

| file | what | producer |
| --- | --- | --- |
| `uc02-pii-corpus.json` | the corpus of record: one row per message (text, contact, scenario, channel, density, renderer, verification, planted strings, near misses) | `python -m ucs.uc02_pseudonymization.code.pii_corpus --renderer model --provider codex --force --force-llm` |
| `uc02-pii-gold.jsonl` | its answer key: one span per line (offsets, type, surface, canonical form, form label, `inflected`, `entity_id`, canary flag) | same run |
| `corpus-manifest.json` | what the record was generated from: corpus id, n, seed, renderer, provider / model / tier, contact count, hashes, flagged messages | same run |
| `uc02-pii-corpus-mock.json`, `uc02-pii-gold-mock.jsonl`, `corpus-manifest-mock.json` | the offline backup: the same plan rendered from sentence templates, no model call | `… --renderer mock --as-backup --force` |

Both renderings share the plan (seed 42 → the same contacts, values and inflected
name forms), so their gold values coincide; only the prose differs. The current record was model-rendered on 2026-09-05; the separate mock pair remains an offline comparator. Read each manifest to identify the renderer rather than inferring it from a filename.

## Readers

| reader | reads |
| --- | --- |
| `eval/run_table.py` (the detection table) | corpus + gold of record |
| `eval/live_check.py` (the sandwich live check) | corpus + gold of record |
| `eval/nametag3_adapter.py` | corpus of record |
| `thesis-dm-frontend/bridge/routes_uc02.py` `/uc02/samples` | corpus of record |
| `tests/` | nothing here; they build tiny corpora |

## Types

PERSON (nominative and one oblique form, `inflected: true`), EMAIL, PHONE, ADDRESS
(street, postal code, town as one span), DATE (birth date), BBAN (domestic account),
IBAN_CZ, ORG (employer), ICO, DIC, RC (generated for the planted person, since no contact
stores one; its `entity_id` is that contact's id, like every other value of the person). About 5 %
of the messages carry an IČO with a wrong check digit as a negative control
(`near_misses`, never in the gold).
