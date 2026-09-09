# `translation/` — the one-time translation result (FROZEN)

`stage1-translate.json` is the output of the single paid run of Google Cloud
Translation v3 on 2026-05-29. It is the only translation the substrate has and
the normal build reuses it without another translation call. md5 of the plain file `3d009f5a6a2f242174479997e3935f8a`. Git tracks it as
`stage1-translate.json.gz` (81 MB, deterministic gzip); the plain file is unpacked by `build_all`
or `python -m substrate.pipeline.packing --unpack`.

## What is inside

A JSON object keyed by item id (121 781 keys). Each value:

| field | meaning |
| --- | --- |
| `item_id` | `rs::<reviewerID>::<asin>::<unixReviewTime>` review summary, `rt::…` review text, `pt::<asin>` product title |
| `kind` | `review_summary` / `review_text` / `product_title` |
| `source_user_id` | reviewer id (null for product titles) |
| `en` | the English text exactly as it was sent (decoded but not cleaned; see `../pre-clean-2026-09-02/`) |
| `cz_raw` | the Czech translation as returned, or empty when the call failed |
| `attempts` | always 1 (no retry was implemented) |
| `error` | null, or the API error: 8 080 × quota `429 RESOURCE_EXHAUSTED`, 14 × `400 Text is too long` |

113 687 items translated (93.4 %): 48 342 summaries, 48 277 texts, 17 068 titles.
Google Translate inserted 11 002 zero-width spaces into 4 794 `cz_raw` values;
they are kept here and removed when the chain reads the file.

## How the chain uses it

Code paths start at the repository root; `amazon/` and `intermediate/` below are under `substrate/snapshots/`. Commands run from the root.

`substrate/pipeline/build_clean_snapshots.py` joins Czech text into
`amazon/amazon-translated-cz.json` by item id and cleans it with
`utils.text_hygiene.clean_text`. Reviews without any Czech text are dropped
(2 964 in the original assembly); a review with only one half translated keeps
the other field empty. That historical count is not the current 425-reviewer
coverage: consult `substrate/snapshots/amazon/translation-coverage.json`.
`substrate/pipeline/build_english_snapshot.py --check-against-frozen` proves every
item in the rebuilt queue `intermediate/english-items.jsonl` has a record here (which may contain a failed translation).
Since the 2026-09-03 restratification the queue covers 425 of the 500 reviewers
listed in `frozen-reviewers.json` next to this file; the rest stay here as
evidence, and the stratification may not select outside that list.
Current UC-04 methods read the assembled database, not the retired direct-translation handoff.

## Facts of the run and why this translator

Run parameters, failure causes and per-reviewer coverage:
[Translation pipeline](../../../pipeline/translation_pipeline/README.md) and
`amazon/translation-coverage.json`. The trials that chose this translator over
LLM translators and local models: `bakeoff-2026-05/` (next to this file).
