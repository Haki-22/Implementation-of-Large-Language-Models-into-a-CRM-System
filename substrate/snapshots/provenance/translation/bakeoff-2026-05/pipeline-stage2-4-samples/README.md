# pipeline-stage2-4-samples: the translation pipeline's own stage 2-4 outputs

The original translation design had five stages; the current build reuses its frozen stage-1 output. Only stage 1 ran on the
full corpus; stages 2-4 ran on samples during development and stage 3 partially on the full
corpus. These are those outputs.

| file | content |
| --- | --- |
| `stage2-comet.csv` | stage 2 COMET-Kiwi on a 30-item sample: `item_id, comet_score, status, attempt` |
| `stage3-gemini-judge.csv`, `stage3-gemini-flash-judge.csv` | stage 3 judge on 20 items: `item_id, verdict, fixes_json` |
| `stage4-sonnet-judge.csv`, `stage4-haiku-judge.csv` | stage 4 second-judge on the same 20 items |
| `stage4-sonnet-judge-v2-30items-legacy.csv` | earlier prompt version of the stage-4 judge (`verdict, reason, suggested_fix`) |
| `multi-model-judge-comparison-20items.csv` | the 20 items with all verdict columns side by side |
| `phase3_verdicts/` | the partial full-corpus judge runs: Gemini INVALID verdicts (481, run stopped at 22 % of the corpus with a billing error), Opus INVALID verdicts (314) with `opus_chunks_meta.json` and `opus_summary.json` (chunked over 113 687 items, most chunks failed on the client side) |

## Did the shipped corpus pass this gate?

No. Stages 2-4 ran on samples during development and stage 3 partially on the full corpus. The
full-corpus translation exhausted the project's credit: the Gemini judge stopped at 22 % of the
chunks with a billing error and the Opus chunked run failed on the client side, so the shipped
Czech text is stage 1 as is, without COMET filtering or judge gating.

The [bake-off overview](../README.md) places these incomplete attempts alongside the other trials.
