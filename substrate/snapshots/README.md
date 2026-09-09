# `substrate/snapshots/` — versioned substrate data

Every JSON / SQLite artifact the substrate produces or consumes.
Co-located with the code that generated it (`substrate/generators/` +
`substrate/pipeline/`) so the chain of provenance is one tree.

## Structure

```
snapshots/
├── substrate.db                ← the CRM database UC-01, UC-03 and the frontend read
│                                 (UC-04's arena reads the database too, since 2026-09-06). Gitignored,
│                                 regenerable from the JSON files below in ~15 s.
├── contacts/                   ← outputs of `python -m substrate.generators`
│   ├── contacts.json    (500 Czech contacts; the first 425 carry a reviewer_id, 75 are prospects)
│   ├── companies.json                  (8 partner companies with IČO/DIČ/address, `generators/companies.py`, written by `python -m substrate.generators`; required by the assembler)
│   └── notes.json                      (80 seeded Czech CRM notes, `generators/notes/`, written by `python -m substrate.generators`; required by the assembler)
├── amazon/                     ← clean canonical Amazon-derived snapshots
│   ├── amazon-original-en.json     (≈93 MB plain, in git as .json.gz 32 MB; English reviews of the 425 linked reviewers, text cleaned)
│   ├── amazon-translated-cz.json   (≈92 MB plain, in git as .json.gz 33 MB; Czech reviews from the frozen translation; untranslated reviews dropped)
│   ├── amazon-catalog-en.json      (≈22 MB plain, in git as .json.gz 7 MB; 18 213 products: title, category, price, description; repaired)
│   ├── amazon-catalog-titles-cs.json (asin -> Czech product title from the frozen translation, 16 067 products, cleaned; the assembler puts it into Product.name_cs)
│   ├── translation-coverage.json   (per reviewer: English vs. Czech review counts, loss ratio)
│   └── reviewer-gender.json        (per reviewer: Amazon name, name-based and cue-based gender, final verdict; 305 of 425 known.
│                                     Written by build_all step `reviewer_gender`, read by `python -m substrate.generators` to pair contacts and reviewers by gender)
├── briefs/
│   └── message_briefs.json     (26 UC-01 outreach briefs, Czech)
├── ocean/
│   └── ocean_synthetic_500.json     (the generator's pre-inference OCEAN state: 326 of 500 have one, 174 empty by design; evidence, no code reader)
├── intermediate/               ← regenerable working layer, NOT tracked in git (build_all step `english` rebuilds it)
│   ├── english-amazon.json     (≈116 MB; cleaned English snapshot)
│   └── english-items.jsonl     (≈111 MB; per-item EN texts = the translation queue)
└── provenance/                 ← FROZEN evidence, never regenerated; each folder has its own README
    ├── translation/                  stage1-translate.json — the one-time translation result
    │                                 (≈233 MB plain, in git as .json.gz 81 MB; md5 of the plain file 3d009f5a6a2f242174479997e3935f8a); read by the chain
    ├── translation/bakeoff-2026-05/  translator + judge trials that chose Google Cloud Translation v3; stage 2-4 samples
    ├── translation/frozen-reviewers.json   the 500 reviewer ids the paid run covers = the only pool the stratification may select from
    ├── translation/judge-stages-unused/    incomplete judge-stage experiments; not a full-corpus gate, not current entry points
    ├── contact-enrichment-trial-2026-05/   nine rows (3 contacts x 3 providers) of the dropped LLM enrichment branch; nothing reads them
    ├── pre-clean-2026-09-02/         the record of the six snapshots as used BEFORE the cleaning: checksums, the trace
    │                                 script + report, and the one irreproducible copy (contacts, .json.gz); the five
    │                                 regenerable copies were removed 2026-09-03 (its _PROVENANCE.md says how to rebuild them)
    └── ocean-inference-2026-05-29/   what Gemini said about the OCEAN profiles (62 inferred vs the 323 sampled at the time) + CLI trial output
```

## How to use

Commands below run from the repository root; tree entries are relative to this folder. UC-02's corpus and gold spans live separately in `ucs/uc02_pseudonymization/snapshots/`.

UC-03's tools and the frontend read `substrate.db` with plain `sqlite3`; UC-01's
demo CLI reads it through `substrate.schema.session`. To regenerate the database
from the committed JSON snapshots:

```bash
python -m substrate.pipeline.build_all --force --from database   # ~45 s incl. audit gate + manifest
```

Individual snapshot files can be opened with any JSON reader; the `amazon/`
review files are large (~90 MB each) so prefer
`substrate/pipeline/amazon_lookup.py` for indexed access.

## Outputs

This directory is the persistent state — nothing in it is generated
on demand by the runtime. The reader-to-file map:

| Reader | Files |
| --- | --- |
| `substrate/pipeline/build_substrate_db.py` | `contacts/`, `amazon/` (incl. `amazon-catalog-titles-cs.json`), `briefs/`, plus `ucs/uc01_personalization/snapshots/ocean_inferred.json` and UC-04's `results/uc04_to_uc01_handoff.json` |
| `substrate/pipeline/build_english_snapshot.py` | `../pipeline/data_acquisition/stratified_500_users.json`; `--check-against-frozen` reads `provenance/translation/stage1-translate.json` |
| `substrate/pipeline/build_ocean_synthetic.py` | `contacts/contacts.json` |
| `substrate/pipeline/build_reviewer_gender.py` | `intermediate/english-amazon.json` -> writes `amazon/reviewer-gender.json` |
| `python -m substrate.generators` (the `contacts` step) | `intermediate/english-amazon.json` + `amazon/reviewer-gender.json` -> writes `contacts/` |
| `substrate/pipeline/build_clean_snapshots.py` | `intermediate/english-amazon.json` + `provenance/translation/stage1-translate.json` + `../pipeline/data_acquisition/downloaded/meta_Electronics.json.gz` |
| `substrate/pipeline/data_acquisition/fetch_and_filter.py` | `provenance/translation/frozen-reviewers.json` (the candidate pool of the stratification) |
| `substrate/pipeline/amazon_lookup.py` (helper) | `amazon/amazon-original-en.json` by default, any reviewer file by path |
| `ucs/uc01_personalization/` (generate, picker, metrics, ocean_inference) | `substrate.db` only |
| `ucs/uc02_pseudonymization/eval/false_alarms.py` | `substrate.db` (`uc_reviews`) |
| `ucs/uc04_matchmaker/` | `substrate.db` for the arena and for the outputs for UC-01 (`outputs_for_uc01/`); UC-04 parses no JSON snapshot |
| `thesis-dm-frontend/bridge/` routes | `substrate.db` and the UC-02 corpus under its own package |
| UC-01 demo CLI, UC-03 tools, UC-04 arena, frontend bridge | `substrate.db` |

Notes:

- `substrate.db` is gitignored; rebuild on demand.
- **`provenance/` is frozen evidence** (see `provenance/_PROVENANCE.md`): the one-time
  translation result the chain joins against, the bake-off that chose the translator, the six
  snapshots exactly as used before the 2026-09-02 cleaning (including the queue sent to the
  translator, dirty), and the contacts before the OCEAN backfill. Nothing in it is regenerated
  by any script; the audit gate excludes it on purpose. The raw dumps in
  `../pipeline/data_acquisition/downloaded/` are the origin of everything; the three-stage trace that
  reproduces the dirty state from them is
  `provenance/pre-clean-2026-09-02/trace_bad_chars.py` (output `provenance-trace.md` next to it).
- **Large files travel compressed.** Git tracks `amazon/*.json.gz`, `provenance/translation/stage1-translate.json.gz`
  and the pre-clean contacts copy as `.gz`; the plain `.json` next to each is gitignored and materialised by
  `build_all` (both modes) or `python -m substrate.pipeline.packing --unpack`. `substrate/pipeline/packing.py`
  writes deterministic gzip; compressed bytes remain stable when the uncompressed input is unchanged.
- `intermediate/` is regenerated by `build_english_snapshot.py` and not tracked in git; normal work does not read it.
- `data_acquisition/downloaded/` (under `../pipeline/`, not here) holds the two Amazon
  `*.gz` source files and the ČSÚ / Czech Post files: not tracked, md5-pinned, fetched by
  `build_all --force` when missing.
- All Czech-translation QA artifacts (COMET CSVs, judge verdicts,
  `phase3_verdicts/`) were retired during consolidation; the canonical
  Czech text is whatever made it into `amazon/amazon-translated-cz.json`.

## Next step

- `../pipeline/README.md` — the scripts that produce these files.
- `../schema/README.md` — the SQLModel entities the snapshots populate.
- `../README.md` — substrate overview.
