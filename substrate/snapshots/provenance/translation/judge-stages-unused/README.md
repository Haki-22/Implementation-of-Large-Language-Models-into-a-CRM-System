# Translation stages 3-5 — incomplete quality-gate experiments

Frozen evidence, moved here on 2026-09-03. **Not runnable code**: it is kept so
the design of the translation quality gate is on the record, not so anyone
executes it. Like everything under `snapshots/provenance/`, it is never
regenerated and is excluded from the text-hygiene audit gate.

## What these were

The translation pipeline was designed as five stages: translate, score, judge,
judge again, assemble with a human-in-the-loop queue.

| File | Stage | Role |
| --- | --- | --- |
| `stage3_gemini_judge.py` | 3 | Gemini JSON judge over the (en, cz) pairs COMET flagged |
| `stage4_sonnet_judge.py` | 4 | Second, independent Sonnet JSON judge for agreement |
| `stage5_assemble.py` | 5 | HITL queue for disputed items + final assembly of `czech-amazon.json` |
| `_judge_common.py` | 3 + 4 | Shared judging loop, batching, JSON parsing, CSV writing |
| `prompts_translation.py` | 3 + 4 | The judge prompts |
| `orchestrator.py` | all | Chained stages 1-5 into one resumable run |

## Why they are here rather than in the live tree

They ran during the translator bake-off (`../bakeoff-2026-05/`) on samples, and
that is where their results are recorded. There was **no completed full-corpus judge gate**: partial attempts are
retained with the bake-off evidence, but stage 5 never executed, and the shipped `amazon-translated-cz.json` takes `cz_raw` from
stage 1 as is. Stage 3 additionally cannot run at all any more — it targets
Vertex Gemini, decommissioned 2026-05-29.

Their trial results can be inspected, but they cannot support a claim that the
shipped corpus passed a model-judge quality gate.

What replaced them, in evidence terms: the bake-off above (why Google Cloud
Translation was chosen, judge agreement on samples, the retry study) and the
COMET experiment at
`substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/`,
which scored a small matched subset automatically, without an LLM judge.

## What stayed live

`stage1_translate.py` (the frozen run's producer, self-locked behind
`--unfreeze` and the model-call switch), `comet_extract_pairs.py` (pair export)
and `comet_score.py` (local COMET-Kiwi scoring), plus `io_utils.py`. The earlier
`stage2_comet.py` gate is retired. See the [current pipeline guide](../../../../pipeline/translation_pipeline/README.md). The modules in this directory still import names that
were removed from `io_utils.py`; that is expected of frozen evidence.
