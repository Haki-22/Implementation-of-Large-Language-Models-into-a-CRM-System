# UC-02 casing comparison

Source run: `eval/runs/2026-09-07-lemma-table-model-corpus-5-configs/` · corpus: uc02-corpus-v2-model (100 messages, 345 planted items) · 2026-09-07

Strict F1 (exact span and type) of the rule layer + one NER backend under each transform of the corpus: as written, lower case, upper case, lemma (every word replaced by its simplemma lemma, names untouched), lemma_lower. PERSON and ADDRESS are the strict F1 of that type under lower. Drop = F1 as written minus F1 under lower.

| configuration | licence | original | lemma | lower | lemma_lower | PERSON lower | ADDRESS lower | drop |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules | — | 0.560 | 0.553 | 0.560 | 0.553 | 0.000 | 0.000 | −0.000 |
| rules + bardsai (default) | Apache 2.0 | 1.000 | 0.939 | 0.914 | 0.859 | 0.856 | 0.718 | −0.086 |
| rules + bardsai_v2 | Apache 2.0 (rolling preview, pinned) | 0.984 | 0.942 | 0.896 | 0.862 | 0.858 | 0.619 | −0.088 |
| rules + gliner2 | Apache 2.0 | 0.869 | 0.841 | 0.869 | 0.841 | 0.773 | 0.895 | −0.000 |
| rules + stulcrad | MIT tag; CNEC 2.0 corpus CC BY-NC-SA | 0.974 | 0.932 | 0.827 | 0.799 | 0.645 | 0.737 | −0.148 |

`DEFAULT_NER_BACKEND` = `bardsai`: the record backend of the detection table. Every number reproduces from the source run folder (`summary.json`, `predictions/`).
