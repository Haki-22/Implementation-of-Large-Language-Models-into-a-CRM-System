# UC-02 casing comparison

Source run: `eval/runs/2026-09-07-casing-table-model-corpus-11-configs/` · corpus: uc02-corpus-v2-model (100 messages, 345 planted items) · 2026-09-07

Strict F1 (exact span and type) of the rule layer + one NER backend on the corpus as written, in lower case and in upper case. PERSON and ADDRESS are the strict F1 of that type in lower case. Drop = F1 as written minus F1 in lower case.

| configuration | licence | original | lower | upper | PERSON lower | ADDRESS lower | drop |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rules | — | 0.560 | 0.527 | 0.560 | 0.000 | 0.000 | −0.033 |
| rules + bardsai (default) | Apache 2.0 | 1.000 | 0.894 | 0.882 | 0.856 | 0.718 | −0.106 |
| rules + bardsai_v2 | Apache 2.0 (rolling preview, pinned) | 0.984 | 0.874 | 0.853 | 0.858 | 0.619 | −0.110 |
| rules + gliner2 | Apache 2.0 | 0.869 | 0.848 | 0.869 | 0.773 | 0.883 | −0.022 |
| rules + wismut | MIT | 0.974 | 0.834 | 0.754 | 0.622 | 0.974 | −0.140 |
| rules + stulcrad | MIT tag; CNEC 2.0 corpus CC BY-NC-SA | 0.974 | 0.804 | 0.952 | 0.645 | 0.737 | −0.170 |
| rules + wismut_small | MIT | 0.950 | 0.765 | 0.690 | 0.492 | 0.895 | −0.185 |
| rules + snerta | Apache 2.0 (source-corpus terms apply) | 0.774 | 0.728 | 0.734 | 0.880 | 0.000 | −0.046 |
| rules + bardsai_mini | not stated on the card | 0.968 | 0.714 | 0.697 | 0.455 | 0.575 | −0.254 |
| rules + richielo | CC BY 4.0 | 0.734 | 0.712 | 0.734 | 0.945 | 0.000 | −0.022 |
| rules + presidio | MIT | 0.382 | 0.320 | 0.503 | 0.086 | 0.000 | −0.062 |

Failed to load: `rules+gliner` (NER backend 'gliner' failed: int() argument must be a string, a bytes-like objec)

`DEFAULT_NER_BACKEND` = `bardsai`: the record backend of the detection table. Every number reproduces from the source run folder (`summary.json`, `predictions/`).
