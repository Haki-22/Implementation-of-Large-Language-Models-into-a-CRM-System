# UC-02 NER comparison

Source run: `eval/runs/2026-09-05-detection-table-mock-corpus-23-configs/` · corpus: uc02-corpus-v2-mock (100 messages, 345 planted items) · 2026-09-05

Strict F1 = exact span and type; partial credits a half-found address. The four type columns are strict F1 with the rule layer. Standalone = the NER alone, no rules. Time = detection over the corpus.

| NER backend | licence | rules + NER F1 | partial | PERSON | ADDRESS | ORG | DATE | standalone F1 | time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules alone | — | 0.560 | 0.703 | 0.000 | 0.000 | 0.000 | 0.000 | — | 0 s |
| bardsai (default) | Apache 2.0 | 0.996 | 0.999 | 0.996 | 1.000 | 0.947 | 1.000 | 0.716 | 6 s |
| wismut | MIT | 0.984 | 0.993 | 0.984 | 1.000 | 0.821 | 1.000 | 0.701 | 6 s |
| stulcrad | MIT tag; CNEC 2.0 corpus CC BY-NC-SA | 0.983 | 0.994 | 1.000 | 1.000 | 0.714 | 1.000 | 0.659 | 11 s |
| bardsai_mini | not stated on the card | 0.977 | 0.991 | 0.981 | 0.897 | 0.927 | 1.000 | 0.696 | 2 s |
| bardsai_v2 | Apache 2.0 (rolling preview, pinned) | 0.950 | 0.984 | 0.996 | 0.605 | 1.000 | 1.000 | 0.661 | 4 s |
| wismut_small | MIT | 0.945 | 0.972 | 0.920 | 1.000 | 0.769 | 0.200 | 0.638 | 4 s |
| gliner2 | Apache 2.0 | 0.908 | 0.908 | 0.830 | 0.987 | 0.623 | 1.000 | 0.551 | 16 s |
| gliner | Apache 2.0 (weights CC BY-NC-SA) | 0.829 | 0.869 | 0.844 | 1.000 | 0.092 | 0.667 | 0.498 | 22 s |
| snerta | Apache 2.0 (source-corpus terms apply) | 0.784 | 0.889 | 1.000 | 0.000 | 0.895 | 0.000 | 0.477 | 8 s |
| richielo | CC BY 4.0 | 0.703 | 0.836 | 0.944 | 0.000 | 0.136 | 0.000 | 0.362 | 2 s |
| presidio | MIT | 0.370 | 0.573 | 0.140 | 0.000 | 0.000 | 0.000 | 0.292 | 2 s |

`DEFAULT_NER_BACKEND` = `bardsai`: the best hybrid among licences a CRM vendor could use. Every number reproduces from the source run folder (`summary.json`, `predictions/`).
