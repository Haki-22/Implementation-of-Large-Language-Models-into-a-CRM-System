# Translation pipeline — FROZEN (ran once, 2026-05-29)

The English→Czech translation of the Amazon layer is a one-time, paid run.
The normal build never re-runs it: the result is a committed artifact and every downstream
step joins against it by item id.

| Fact | Value |
| --- | --- |
| Ran | 2026-05-29, Google Cloud Translation v3 (`stage1_translate.py`, concurrency 8, no retry) |
| Input | `snapshots/intermediate/english-items.jsonl` (the copy actually sent, un-cleaned, survives verbatim as the `en` field of the frozen file; the separate copy was removed on 2026-09-03, md5 in `snapshots/provenance/pre-clean-2026-09-02/_md5sums.txt`) — 121 781 items: 51 503 review summaries, 51 457 review texts, 18 821 product titles (the original frozen cohort; the current build uses a subset) |
| Output | `snapshots/provenance/translation/stage1-translate.json` — frozen; md5 `3d009f5a6a2f242174479997e3935f8a` (also in `substrate/snapshots/README.md`). Translator and judge trials that led to this design: `snapshots/provenance/translation/bakeoff-2026-05/` |
| Translated | 113 687 items (93.4 %): 48 342 summaries, 48 277 texts, 17 068 titles |
| Failed | 8 080 × `429 RESOURCE_EXHAUSTED` (characters-per-minute quota), 14 × `400 Text is too long` (reviews > 31 000 characters). Every item has `attempts == 1`. |
| Consequence | 14 reviewers lost all reviews, 27 lost part of them (per-reviewer batching). Coverage per reviewer: `snapshots/amazon/translation-coverage.json`. |
| Stages 3–5 | The two LLM judges and the human-in-the-loop (HITL) assembly ran only in the translator bake-off; the shipped Czech snapshot bypasses them and takes `cz_raw` from stage 1 as is. Moved to `snapshots/provenance/translation/judge-stages-unused/` on 2026-09-03 as frozen evidence — stage 3 also targets Vertex Gemini, decommissioned. Stage 2 is now a plain quality report: `comet_extract_pairs.py` pulls the translated pairs out of the frozen file and the portable `comet_score.py` scores them with COMET-Kiwi (CPU here, GPU anywhere); the PASS / RETRY / HITL loop of the old `stage2_comet.py` was retired on 2026-09-03 because it belonged to the judge design. The clean-input experiment used the same scorer, see `experiments/clean-input-comet-2026-09-03/`. |
| Input state at run time | The queue sent to the translator was **decoded but not cleaned**: the step that built it only unescaped HTML entities, so the characters Amazon ships as entities were present in the English text (7 U+FFFD, 9 private-use Wingdings glyphs, 94 NBSP, 9 line separators, 1 C1 control, 1 zero-width, 4 mojibake, in 140 of 121 781 items). The frozen file preserves that exact input in its `en` field, which is the evidence. Those 140 items had 13 failures (9.3 %, against 6.6 % for other items). This observational difference does not identify the cause of failure or measure translation quality. Since 2026-09-02 `build_english_snapshot.py` cleans the text before queueing: same item ids, clean text, frozen file untouched. Full trace from the compressed dumps: `snapshots/provenance/pre-clean-2026-09-02/provenance-trace.md`. |
| Known artifact | Google Translate inserted 11 002 zero-width spaces into 4 794 Czech outputs (the English input had 1); `build_clean_snapshots.py` removes them with `utils.text_hygiene.clean_text`. The frozen `cz_raw` keeps them. |

Paths beginning with `snapshots/` in the table are relative to `substrate/`. They describe the original May cohort, not the smaller current 425-reviewer selection.

## Was the un-cleaned input a problem?

Measured, not assumed: `experiments/clean-input-comet-2026-09-03/` scores the 32
translated items whose English carried a hidden character against 96 matched
clean controls. COMET-Kiwi delta **+0.011** (95 % CI [−0.036, +0.058], p = 0.93)
— no degradation was detected in this small automatic-score comparison.
The groups contain different items, not paired retranslations of the same input.
This does not establish equivalence, causality or the absence of individual errors.

`stage1_translate.py` refuses to run without `--unfreeze`. The upstream queue
is rebuilt by `build_english_snapshot.py`; its `--check-against-frozen` flag
proves the rebuilt queue contains only item ids present in the frozen record.

## Scoring the whole corpus (optional quality report, no gate)

A full-corpus COMET-Kiwi report would describe automatic scores, not certify the
translations. It is not part of the normal build or a completed result claimed
here. Scoring requires an optional environment with `unbabel-comet` and access
to the `Unbabel/wmt22-cometkiwi-da` model. The package is not included in the
main requirements; use an isolated scoring environment so its dependency
constraints do not change the working prototype. Saved scores can be read
without it.

From the repository root, first export pairs from the unpacked frozen record:

```bash
python -m substrate.pipeline.translation_pipeline.comet_extract_pairs
```

This writes `substrate/snapshots/intermediate/comet-pairs.jsonl.gz` (113 687
pairs). In the scoring environment, run from the same root. Start with the
128-pair reference comparison, then optionally score all pairs:

```bash
python -m substrate.pipeline.translation_pipeline.comet_score \
    --pairs substrate/snapshots/intermediate/comet-pairs.jsonl.gz \
    --out comet-smoke-new.csv --gpus 0 \
    --ids-from substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/scores.csv \
    --check substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/scores.csv

python -m substrate.pipeline.translation_pipeline.comet_score \
    --pairs substrate/snapshots/intermediate/comet-pairs.jsonl.gz \
    --out comet-full-new.csv --gpus 0
```

Choose unused output names: the scorer writes the CSV and its
`.run-info.json` metadata. Keep both with the exact input pairs. On a separate
GPU machine, copy the standalone `comet_score.py`, pairs file and reference CSV,
adjust their paths, and use `--gpus 1` with a compatible GPU environment.
The recorded CPU rate was about 2.5 pairs/s; throughput and numerical agreement
depend on hardware, dependencies and batch size. These commands perform new
inference and may download weights; they do not merely reproduce a saved table.
