# Did the un-cleaned translator input cost translation quality?

A matched observational comparison recorded on 2026-09-03. It scores existing
translations; it does not retranslate the same source before and after cleaning.

## The question

The English queue sent to Google Cloud Translation on 2026-05-29 was decoded but
not cleaned: the step that built it only unescaped HTML entities, so characters
Amazon ships as entities survived into the text the translator saw. Since
2026-09-02 `build_english_snapshot.py` cleans the text before queueing.

That leaves an open question about the shipped Czech corpus: **would it have
been better if the input had been clean?** The affected items had a higher observed API failure rate,
but that comparison does not establish why they failed. Whether the ones that
_did_ translate came out worse had never been measured.

## Method

Comparing the shipped corpus against itself, which needs no API call and no
spend:

1. `build_pairs.py` walks the exact queue that was sent — the `en` field of the
   frozen `snapshots/provenance/translation/stage1-translate.json` preserves it
   verbatim (the separate copy was removed on 2026-09-03) — and flags every item
   whose English carried a hidden character — the classes
   `utils.text_hygiene` calls critical, plus NBSP / LSEP / SHY. Cosmetic classes
   (double spaces, leftover entities, foreign scripts) are excluded by this
   experiment's selection rule; their effect is not tested here.
2. For each flagged item it draws **3 matched controls** from the clean items:
   same `kind` (product title / review summary / review text) and the nearest
   English length, each control used once. Deterministic, no RNG.
3. `score_pairs.py` scores every pair with **COMET-Kiwi**
   (`Unbabel/wmt22-cometkiwi-da`) — a reference-free quality estimator, so it
   judges the (English source, Czech output) pair directly and needs no human
   reference translation. Local model, CPU, ~50 s for 128 pairs.

## Result

35 queued items carried a hidden character; 32 of them translated (3 failed).
Class mix: 17 NBSP, 9 PUA (leaked Wingdings glyphs), 9 LSEP, 7 U+FFFD, 3 C0,
2 mojibake, 1 C1, 1 zero-width.

| arm | n | mean COMET | median | sd |
| --- | --: | ---: | ---: | --- |
| dirty input | 32 | 0.7675 | 0.8239 | 0.115 |
| clean input | 96 | 0.7564 | 0.8296 | 0.129 |

**delta (dirty − clean) = +0.0111**, 95 % CI [−0.036, +0.058] ·
Mann-Whitney U = 1519.5, **p = 0.93** · Cohen's d = +0.088.

Per kind (dirty vs clean mean): product title 0.8433 vs 0.8229 · review text
0.6393 vs 0.6204 · review summary 0.7520 vs 0.8732 (n = 2, not interpretable).

## Reading it

The mean score difference is small and its reported confidence interval includes
zero. No degradation was detected in this sample under this automatic metric.
That is not proof that hidden characters do no harm: the groups contain different
items matched by kind and length, not paired retranslations. Unmeasured content
differences, the small affected sample (32 items) and estimator limitations remain.

This evidence cannot establish a causal throughput or quality effect, prove
equivalence, or rule out individual mistranslations. Input cleaning remains useful
independently of this comparison; whether retranslating an item improves it would
require a paired experiment or human review.

## Files

| File | What |
| --- | --- |
| `build_pairs.py` | Selects the dirty items and their matched clean controls → `pairs.csv` |
| `score_pairs.py` | Scores every pair with COMET-Kiwi → `scores.csv` |
| `pairs.csv` | arm, item_id, kind, en_len, hidden_classes |
| `scores.csv` | the same plus `comet_score` |

To repeat inference, run from the repository root in a disposable copy. These
scripts overwrite `pairs.csv` and `scores.csv`; the local scorer may download model
weights and requires its model access/dependencies. Reading the saved CSV files
requires neither inference nor a hosted model call:

```bash
python substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/build_pairs.py
OMP_NUM_THREADS=4 nice -n 19 python \
  substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/score_pairs.py
```
