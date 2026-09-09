# hermes_triple-translator-100x3: three translators on the same 100 reviews

100 review items (group B reviewers) translated independently by Google Cloud Translation v3,
Claude Opus 4.7 and Gemini 3.1 Pro, then scored and judged. This is the experiment behind the
translator choice.

| file | content |
| --- | --- |
| `translations.jsonl` | 300 rows: `item_id`, `translator` (`vertex-cloud-translation-v3` = Google Cloud Translation v3, `claude-opus-4-7`, `gemini-3.1-pro-preview`), `en`, `cz`, `error` |
| `comet_scores.csv` | COMET-Kiwi score per (item, translator): `item_id, translator, comet_score, status` |
| `judge_opus_one-shot.csv`, `judge_gemini31_one-shot.csv` | one-shot judge verdicts (`VALID` / `INVALID` + `fixes_json`), all 300 pairs in one call per judge |
| `batch15_baseline/judge_*_verdicts.csv` | the same judges run in batches of 15 items; the batched Opus judge rejected 82 % of its own translations, which is why one-shot judging was adopted |

Headline: mean COMET-Kiwi 0.762 (Google Cloud Translation v3) vs 0.750 (Opus) vs 0.742 (Gemini).

## Was it used for the frozen translation?

**Google Cloud Translation v3: yes**, chosen as the only translator of the full run. Opus and
Gemini as translators: no. Reasons: highest COMET-Kiwi mean, median and PASS rate; roughly six
times faster per item; the only option affordable for 121 781 items; no formatting artifacts
(Opus kept an `EN:` prefix in outputs, Gemini glued words and left `hi-res` untranslated).
94 of the 100 Google outputs here are byte-identical to the frozen output for the same items
(`../../stage1-translate.json`), the remaining 6 differ by wording, which
is the service's known non-determinism.

See the [bake-off overview](../README.md) for the other trials and the limits of automatic scoring.
