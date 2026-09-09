# `uc01_personalization/snapshots/` — UC-01 artifacts

Everything here is downstream of `substrate/snapshots/substrate.db`, which owns
the CRM content. UC-01 keeps only what it selected, what it generated, and one
input the database build takes back from it.

## Structure

```
snapshots/
├── picks/
│   └── uc01-personalization-20-level.json          who the reported runs are for: the rule, the ids per cell with their data tier, the defective rows, the briefs
│                                 (written by `python -m ucs.uc01_personalization pick`)
├── runs/
│   └── <run-id>/                one folder per run (`... run`): config.json, pick.json, messages.jsonl,
│       │                         results.csv, summary.json; `evaluate` adds metrics.csv + metrics-summary.json
│       └── judge-<id>/          one folder per judging of that run (`... judge <run-id>`): config.json (level,
│                                 judges + arbiter with resolved models, subset), verdicts.jsonl (one trail per
│                                 message), summary.json, human-review.md (the HUMAN and PARTIAL rows to fill in)
│   └── <date>-ocean-inference-<provider>-<model>-<tier>-<N>-contacts/   one folder per OCEAN inference batch
│                                 (`ocean_inference infer`): config.json, targets.json, responses/, status.csv, profiles.json, RESULTS.md
├── ocean_inferred.json          OCEAN profiles inferred from the English reviews, keyed by reviewer id, written by
│                                 `ocean_inference freeze` from run folders (each entry names its run); the database
│                                 build loads the numbers into Contact.ocean with ocean_source = 'inferred'
├── uc01-judge-testset.json      the 100-message calibration set for the judges (`judge_testset.py`)
```

## Producers and readers

Commands run from the repository root; paths in the tree are relative to this folder. See the [UC-01 guide](../README.md) before running a producer. The September 7 ladder record lacks a database hash; computing one now would not recover that missing provenance.

| file | written by | read by |
| --- | --- | --- |
| `picks/*.json` | `python -m ucs.uc01_personalization pick` | `run`, `faithfulness`, `ocean_inference infer --pick`, UC-04 `sample` (the pick's contacts go first) |
| `runs/<run-id>/*` | `run`, `evaluate`, `faithfulness` | `report`; the chapter's tables |
| `runs/<run-id>/judge-<id>/*` | `judge <run-id>` | `report`; the human review pass; the chapter's judge tables |
| `runs/<ocean run>/*` | `ocean_inference infer` | `ocean_inference freeze`, `ocean_inference attachment` (→ `attachments/ocean-inference.{csv,md}`); the chapter's provenance of a profile |
| `ocean_inferred.json` | `ocean_inference freeze` (from run folders) | `substrate/pipeline/build_substrate_db.py`; `ocean_inference infer --previous` (who to carry over) |
| `uc01-judge-testset.json` | `ucs.uc01_personalization.judge_testset` | `judge_testset --calibrate`, tests |

New generation and judging create new folders. `evaluate` adds or refreshes metrics in an existing run; report builders can refresh summaries. Preserve the original folder separately when reproducing saved evidence. Mock runs are not kept. The `smoke-*` folders (one contact, all levels) are the evidence of a model choice, never a record; `run --reuse` copies their identical calls into the run of record.
