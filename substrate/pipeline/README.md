# `substrate/pipeline/` — substrate build scripts

Scripts that assemble `substrate/snapshots/substrate.db` from the raw
Amazon dump plus the generators in `substrate/generators/`. Each script
is independently runnable; the canonical end-to-end entry point is
`build_all.py`.

## Structure

```
raw Amazon dumps (data_acquisition/downloaded/*.gz, fetched on demand, pinned by md5, not tracked)
        │  data_acquisition/fetch_and_filter.py  - verify/download; pick 425 stratified reviewers (A=300, B=50, C=75); contacts 426-500 get no reviewer
        ▼
data_acquisition/stratified_500_users.json
        │  build_english_snapshot.py  - clean the original text (utils.text_hygiene), build the translation queue
        ▼
../snapshots/intermediate/{english-amazon.json, english-items.jsonl}
        │  translation_pipeline/  - FROZEN: ran once 2026-05-29 (Google Cloud Translation v3); never re-run
        ▼
../snapshots/provenance/translation/stage1-translate.json  - bilingual EN + CZ per item (FROZEN)
        │  build_clean_snapshots.py  - join frozen CZ + cleaned EN + catalog; same cleaner
        ▼
../snapshots/amazon/{amazon-original-en,amazon-translated-cz,amazon-catalog-en,translation-coverage}.json
        │  (identity layer moved to substrate/generators/__main__.py)
        ▼
../snapshots/contacts/{contacts,notes,companies}.json
        │  build_substrate_db.py
        ▼  (+ ../snapshots/briefs/ and ucs/uc01_personalization/snapshots/ocean_inferred.json)
../snapshots/substrate.db   ← the one SQLite database every UC reads
```

| Script | Role |
| --- | --- |
| `build_all.py` | **The chain.** Runs every step below in order, stops at the first failure, ends with the text-hygiene audit gate and prints a manifest (table row counts + snapshot md5s). `--verify` checks build state and may unpack compressed snapshots, without downloading or rebuilding the database; `--force` rebuilds; `--from <step>` resumes. Start here rather than copying the individual commands. |
| `build_substrate_db.py` | **Canonical assembler.** Loads every committed JSON snapshot and writes `substrate.db`. Pure assembly: every row is sourced from a snapshot, nothing is fabricated at this stage; a missing input (for example the notes snapshot) is an error, never a silent fallback. |
| `build_english_snapshot.py` | `build_all` step `english`: cleans the original Amazon text (`utils.text_hygiene.clean_text`) into `intermediate/english-amazon.json` + the translation queue `english-items.jsonl`; `--check-against-frozen` asserts every queued item has a frozen translation (one-directional: the frozen run may cover more). |
| `build_clean_snapshots.py` | Joins the frozen `stage1-translate.json` + cleaned English layer + product metadata into the `amazon/` snapshots (catalog: mojibake repaired, entities unescaped, HTML stripped) and writes `translation-coverage.json`. |
| `build_reviewer_gender.py` | `build_all` step `reviewer_gender`: estimates gender with local heuristics of each Amazon reviewer behind the substrate from the English review text (first-person gendered forms), writes `snapshots/amazon/reviewer-gender.json`; the contact generator's runner pairs contacts with reviewers by it. `load_reviewer_gender()` is the read side. |
| `amazon_lookup.py` | Read-only helper to index `amazon-original-en.json` by `reviewer_id` so UC code does not rescan the 100 MB file. |
| `packing.py` | Compressed transport: the five snapshots over GitHub's file limit are tracked as `.json.gz` (deterministic gzip) and unpacked to the plain `.json` the code reads — `build_all` does it first thing in both modes, `python -m substrate.pipeline.packing --unpack` by hand. Readers never see the `.gz`. |
| `data_acquisition/fetch_csu.py` | `build_all` step `csu`: downloads (`--download`, ~900 MB, git-ignored, md5-pinned, `--verify-only`) and reduces the ČSÚ open data behind the demographic draws: `data/cz_age_sex.csv` (OBY02B, 1. 1. 2025) and `data/cz_municipalities.csv` (OBY02A, 1. 1. 2026, joined with the Czech Post postal-code list). Both CSVs carry provenance headers and are committed. |
| `data_acquisition/` | `inputs.py`: one status + ensure function over every pinned download (`build_all --force` fetches what is missing through it; the demo frontend can ask the same question). `fetch_and_filter.py`: pinned download (`--download`) / verification (`--verify-only`) of the two SNAP Electronics dumps + ABC stratification. `downloaded/` holds the two `*.gz` files, not tracked: `build_all --force` fetches and verifies them. |
| `translation_pipeline/` | The paid translation is frozen. `comet_extract_pairs.py` exports bilingual pairs and `comet_score.py` produces a local, reference-free COMET-Kiwi quality report. Neither is part of the ordinary build. Incomplete judge stages remain under provenance; they did not gate the shipped corpus. See [translation README](translation_pipeline/README.md) for evidence and limitations. |

## How to use

Run from the repository root after the [root setup](../../README.md#quickstart). The diagram and inventory use paths relative to this directory unless they start with a package name. Rebuilds replace their target snapshots/database; preserve local CRM edits separately.

The committed snapshots in `../snapshots/` are the practical starting
point for everyday work. One command runs the chain, stops at the first
failure, ends with the text-hygiene audit gate and prints a manifest:

```bash
python -m substrate.pipeline.build_all --verify                  # check build state; may unpack snapshots
python -m substrate.pipeline.build_all --force --from database   # re-assemble substrate.db, ~45 s
python -m substrate.pipeline.build_all --force                   # full rebuild from the raw dumps, minutes
```

`--verify` judges freshness by file time, so a byte-identical regeneration of a
snapshot still makes the steps derived from it report `STALE`; re-run those
steps (`--force --from <step>`) if you intend to rebuild their outputs.

The steps it runs, in order. Each is also runnable on its own with the same
flags; the translation is excluded because it is frozen:

```bash
python -m substrate.pipeline.data_acquisition.fetch_and_filter --verify-only        # amazon
python -m substrate.pipeline.data_acquisition.fetch_csu --verify-only               # csu
python -m substrate.pipeline.build_english_snapshot --force --check-against-frozen  # english
python -m substrate.pipeline.build_clean_snapshots --force                          # clean
python -m substrate.pipeline.build_reviewer_gender --force                         # reviewer_gender
python -m substrate.generators --force --snapshots-only                             # contacts
python -m substrate.pipeline.build_ocean_synthetic                                  # ocean
python -m substrate.pipeline.build_substrate_db --force                             # database
python -m utils.text_hygiene audit substrate/snapshots ucs/uc01_personalization/snapshots ucs/uc02_pseudonymization/snapshots --exclude intermediate/ --exclude provenance/ --exclude pre-backfill   # audit gate
```

The `database` step is pure assembly, but it derives three prompt digests per
contact from the Czech reviews (`frequent_words`, `prior_interactions`,
`style_excerpt`) and the lifecycle stage from the order dates. The style
sample is filtered for gendered first-person forms (`_GENDERED_FIRST_PERSON`
in `build_substrate_db.py`): the translator writes "koupil jsem" for nearly
every reviewer, so a body containing such a form is skipped and, when a
contact has no clean body at all, the longest body is kept with those
sentences cut out (the rule and its coverage are documented in `../schema/DB.md`, Contact section).

## Outputs

- `../snapshots/substrate.db` — the one SQLite database every UC reads.
  Gitignored; regenerable from the committed JSON snapshots.
- `../snapshots/contacts/*.json` — written by `substrate/generators/__main__.py`.
- `../snapshots/amazon/*.json` — written by `build_clean_snapshots.py`.
- `../snapshots/intermediate/{english-amazon.json,english-items.jsonl}` — written by
  `build_english_snapshot.py`.
- `../snapshots/provenance/translation/stage1-translate.json` — written once by
  `translation_pipeline/` (frozen; md5 in `../snapshots/README.md`; bake-off evidence in
  `../snapshots/provenance/translation/bakeoff-2026-05/`).
- `data_acquisition/stratified_500_users.json` — written by `fetch_and_filter.py --force` (`build_all` step `amazon`); 425 reviewers despite the historical name; not tracked, regenerated from the dumps.
- `../snapshots/ocean/ocean_synthetic_500.json` — written by `build_ocean_synthetic.py`: the generator's pre-inference OCEAN state, evidence with no code reader.

## Next step

- `../snapshots/README.md` — the artifacts these scripts produce, with
  reader-to-file mapping.
- `../schema/README.md` — SQLModel entities that `build_substrate_db.py`
  populates.
- `../README.md` — substrate overview and design.
