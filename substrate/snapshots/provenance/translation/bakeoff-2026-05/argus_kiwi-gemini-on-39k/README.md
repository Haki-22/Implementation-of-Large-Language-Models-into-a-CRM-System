# argus_kiwi-gemini-on-39k: quality audit of the reused Czech corpus + judge comparison + determinism

Audit of all Czech translations that existed before the full run (16 290 unique EN/CZ pairs,
reused from earlier work), then a series of judge comparisons on samples and a re-translation
study.

| file / folder | content |
| --- | --- |
| `input.jsonl`, `comet_scores.csv` | the 16 290 pairs (`item_id, kind, asin, en, cz`) and their COMET-Kiwi scores (`item_id, comet_score, status`) |
| `clean_input.jsonl`, `clean_comet_scores.csv` | the same after removing mock / pass-through rows (16 181 pairs) |
| `gemini_invalid_verdicts.jsonl`, `clean_gemini_invalid_verdicts.jsonl` | Gemini judge verdicts, only the INVALID ones are stored (`item_id, verdict, fixes`) |
| `chunks_meta.json` | per chunk of the judge run: items, input characters, verdicts, wall time |
| `opus_300sample/`, `codex_300sample/`, `sonnet_300sample/` | the same 300-item sample judged by Claude Opus 4.7, Codex (gpt-5.5) and Sonnet; `meta.json` = model, prompt id, timing; `*_invalid_verdicts.jsonl` = INVALID verdicts |
| `more_judges_300sample/` | Gemini 2.5 Pro / 2.5 Flash / 3.1 Flash-lite / Haiku on the same sample; `extra_vertex_summary.json` = timings and INVALID counts |
| `complete_bakeoff/` | one INVALID-verdict file per judge model for the complete comparison + `summary.json` (wall time, verdict counts, errors) |
| `retry_invalid/` | the 155 items judged INVALID by either Gemini or Opus re-sent to Google Cloud Translation v3: `retry_input.jsonl` (`cz_original` vs `cz`), `determinism_compare.csv` (122 of 155 byte-identical = 78.7 %), re-judged verdicts, `retry_summary.json`, `summary.json` |
| `local_nmt_100sample/` | 100 items translated by Helsinki-NLP OPUS-MT (2.29 items/s) and NLLB (0.29 items/s) beside the Google output (`cz_vertex`), with `summary.json` |

## Was this translation pool used in the frozen dataset?

No, and this is why. The 16 290 pairs are translations that existed before the full run: 16 164
product titles plus 50 summaries and 50 texts, produced by the same Google service in earlier
sessions (the audit is what confirmed they were real API output and not the mock pass-through files
found next to them, which were excluded on the author's instruction: only text that went through
the API). They were imported into the assembly file of the planned stage 5 (39 689 filled slots,
112 551 pending). The final run then translated the **whole** queue through stage 1 anyway,
the frozen file contains 121 781 item records, because stage 1 is resumable only against its own file
and these rows were not in it. When the credit ran out, stage 5 never assembled the full corpus, and
the 2026-06-01 consolidation made the stage-1 file the single source of Czech text. Result: one
translator, one run, one file keyed by item id, no mixing of translations of different age and
provenance. All 16 290 pairs are in the frozen run; 13 844 came back byte-identical and 2 446
differ by wording (85.0 % identical). The separate `retry_invalid/` study found
78.7 % identical outputs among 155 retries; neither is a guarantee of determinism.

The 0.85 % of pairs jointly flagged by COMET-Kiwi and the Gemini judge describes
this earlier pool, not the error rate of the final corpus. The comparisons
informed a planned judge gate, but no full-corpus gate completed. See the
[bake-off overview](../README.md) for the retained experiments and their scope.
