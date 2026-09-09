# Translation bake-off (May 2026): why Google Cloud Translation v3, and the evidence

Before the one-time translation run (2026-05-29) the translator and the judges were chosen
empirically. These folders are the raw outputs of those trials, kept with the data as
provenance of the decision. Read-only. Each folder has its own README describing its files.

## The decision in numbers

The same 100 Amazon reviews (group B) translated three ways and scored with COMET-Kiwi
(`Unbabel/wmt22-cometkiwi-da`, reference-free quality estimate, 0-1), folder
`hermes_triple-translator-100x3/`:

| Translator | mean COMET-Kiwi | median | PASS rate (>= 0.70) |
| --- | --: | --: | --: |
| Google Cloud Translation v3 (NMT) | **0.762** | 0.811 | 69 % |
| Claude Opus 4.7 (LLM) | 0.750 | 0.794 | 66 % |
| Gemini 3.1 Pro (LLM) | 0.742 | 0.788 | 63 % |

What the score means: COMET-Kiwi is a reference-free quality-estimation model. It reads the
English source and the Czech output, no human reference translation, and predicts on a 0-1 scale
how a human rater would score the translation (trained on WMT direct-assessment ratings). The
mean is over the 100 items per translator; the median and the PASS rate (share of items at or
above the 0.70 threshold used by the pipeline's stage 2) are given because the mean alone hides
the spread. The differences here are small, 0.012 and 0.020 points, but consistent across all
three statistics. It is an automatic estimate, not a human evaluation, and it under-rates long
texts (sentence-level calibration), which the judge trials confirmed.

The specialised NMT service scored highest, ran roughly six times faster per item than the LLM
command-line clients, and was the only option priced for 121 781 items. The LLM translators also
produced formatting artifacts (Opus kept an `EN:` prefix in its output; Gemini glued words together
and left `hi-res` untranslated).

Local open models were tried as well (`local_translators_50sample/`, `argus_kiwi-gemini-on-39k/local_nmt_100sample/`):
too slow on CPU for the corpus (0.05 to 0.2 items per second for the GGUF LLMs, 2.3 items per second
for Helsinki-NLP OPUS-MT, 0.3 for NLLB) and not better in quality.

## Judges

- `themis_judges-on-20items/`: four LLM judges plus COMET-Kiwi on the same 20 translations; roughly 40 % INVALID
  verdicts across judges, the two unanimous-INVALID cases dissected.
- `hermes_triple-translator-100x3/`: batched judging (15 items per call) broke Opus as a judge
  (82 % rejection of its own translations); one-shot Gemini 3.1 Pro was the most stable single
  judge. COMET-Kiwi is biased against long texts (sentence-level calibration).
- `argus_kiwi-gemini-on-39k/`: COMET-Kiwi plus a Gemini judge over the whole reused corpus of the
  time (16 290 unique pairs), a 300-item comparison of further judges (Codex, Opus, Sonnet, Haiku,
  Gemini Flash variants), and the retry study: re-translating 155 INVALID items reproduced 122 of
  them byte-identically (78.7 %), i.e. the NMT service is largely deterministic.
- `pipeline-stage2-4-samples/`: the pipeline's own stage 2-4 outputs on samples (COMET, judge CSVs)
  and the partial phase-3 judge runs over the full corpus.
- `upstream_error-translating-catalog/`: 109 catalog items the translation API rejected.

## What was frozen from this

Google Cloud Translation v3 as the only translator, one pass. The full-corpus translation
exhausted the project's credit, so judge gating on the full corpus was not possible (the judge
phase stopped at 22 % with a billing error) and 93.35 % coverage was accepted as final.
Result: [`../stage1-translate.json.gz`](../stage1-translate.json.gz). The incomplete
judge stages and their sample outputs are retained as evidence, not current build steps.

## Which trial informed the frozen dataset

| folder | used in the dataset? | why |
| --- | --- | --- |
| `hermes_triple-translator-100x3/` | **Google Cloud Translation v3: yes**, as the only translator. Opus and Gemini as translators: no. | highest COMET-Kiwi (0.762 vs 0.750 / 0.742), about 6x faster per item, the only option affordable for 121 781 items, no formatting artifacts. 94 of the 100 Google outputs here are byte-identical to the frozen run. |
| `themis_judges-on-20items/` | no completed judge gate was applied | the trial chose Gemini 3.1 Pro one-shot as gating judge and dropped Sonnet (JSON quote failures) and batched Opus (over-rejection); but no full-corpus judge pass completed, see below |
| `argus_kiwi-gemini-on-39k/` | no: the earlier translations were imported into the planned stage-5 assembly file, but the final translation run re-translated the whole queue through stage 1 and stage 5 never ran (credit exhausted); the consolidation of 2026-06-01 made stage 1 the single source | one translator, one run, one file keyed by item id, no mixing of translations of different age and provenance (mock pass-through files found next to the reuse pool were excluded: only API output). All 16 290 pairs are in the frozen run, 13 844 byte-identical, 2 446 differ (85.0 % byte-identical in this comparison; 78.7 % is the separate 155-item retry study). The 0.85 % jointly flagged fraction belongs to that trial; it is not a completed full-corpus quality guarantee |
| `local_translators_50sample/`, `argus…/local_nmt_100sample/` | no | 0.05 to 0.2 items/s on CPU for the GGUF LLMs (Hunyuan output broken by its prompt format), 2.3 and 0.3 items/s for OPUS-MT and NLLB; these are timings from the tested CPU environment, not a hardware-independent speed ratio |
| `pipeline-stage2-4-samples/` | no completed gate; sample and partial full-corpus attempts | the full-corpus translation exhausted the project's credit; the Gemini judge stopped at 22 % with a billing error, the Opus chunked run failed on the client side. The shipped Czech text is stage 1 as is |
| `upstream_error-translating-catalog/` | not applicable | 109 product titles the API rejected; this is an earlier failure sample; the current catalogue also contains 16 067 Czech titles |
