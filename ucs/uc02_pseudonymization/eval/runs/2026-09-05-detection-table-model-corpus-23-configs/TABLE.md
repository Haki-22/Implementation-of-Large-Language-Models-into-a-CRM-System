# UC-02 NER comparison

Source run: `eval/runs/2026-09-05-detection-table-model-corpus-23-configs/` · corpus: uc02-corpus-v2-model (100 messages, 345 planted items) · 2026-09-05

Strict F1 = exact span and type; partial credits a half-found address. The four type columns are strict F1 with the rule layer. Standalone = the NER alone, no rules. Time = detection over the corpus.

| NER backend | licence | rules + NER F1 | partial | PERSON | ADDRESS | ORG | DATE | standalone F1 | time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules alone | — | 0.560 | 0.703 | 0.000 | 0.000 | 0.000 | 0.000 | — | 0 s |
| bardsai (default) | Apache 2.0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.725 | 9 s |
| bardsai_v2 | Apache 2.0 (rolling preview, pinned) | 0.984 | 0.996 | 0.992 | 0.897 | 1.000 | 0.941 | 0.697 | 5 s |
| stulcrad | MIT tag; CNEC 2.0 corpus CC BY-NC-SA | 0.974 | 0.989 | 1.000 | 1.000 | 0.651 | 0.842 | 0.652 | 16 s |
| wismut | MIT | 0.974 | 0.988 | 0.965 | 0.961 | 0.850 | 1.000 | 0.686 | 9 s |
| bardsai_mini | not stated on the card | 0.968 | 0.989 | 0.989 | 0.780 | 1.000 | 0.941 | 0.681 | 2 s |
| wismut_small | MIT | 0.950 | 0.962 | 0.906 | 1.000 | 0.864 | 0.706 | 0.626 | 8 s |
| gliner2 | Apache 2.0 | 0.869 | 0.884 | 0.773 | 0.895 | 0.590 | 0.762 | 0.509 | 16 s |
| gliner | Apache 2.0 (weights CC BY-NC-SA) | 0.792 | 0.803 | 0.763 | 0.962 | 0.261 | 0.571 | 0.482 | 31 s |
| snerta | Apache 2.0 (source-corpus terms apply) | 0.774 | 0.887 | 0.992 | 0.000 | 0.750 | 0.000 | 0.467 | 10 s |
| richielo | CC BY 4.0 | 0.734 | 0.859 | 0.945 | 0.000 | 0.344 | 0.000 | 0.384 | 2 s |
| presidio | MIT | 0.382 | 0.509 | 0.205 | 0.000 | 0.000 | 0.000 | 0.305 | 2 s |

`DEFAULT_NER_BACKEND` = `bardsai`: the best hybrid among licences a CRM vendor could use. Every number reproduces from the source run folder (`summary.json`, `predictions/`).
