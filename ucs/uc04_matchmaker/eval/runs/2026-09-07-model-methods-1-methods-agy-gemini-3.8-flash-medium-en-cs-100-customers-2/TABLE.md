# UC-04 model methods — 2026-09-07-model-methods-1-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers-2

Sample `model-arms-100`: 100 customers; provider agy / gemini-3.8-flash / medium (CLI 1.1.27); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random).

## `rank_candidates` — Model ranks the candidates alone

whole history + the 101 sampled candidates in a seeded random order; the model returns the full permutation; no classical input. ML input: none.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | 100 | 94 / 6 / 0 (100 reused) | 64 / 100 | 64.0 % (54.2 %–72.7 %) | 0.3833 | 0.3046 | — | 28 / 100 | 34 / 100 |
| cs | sampled | 100 | 90 / 10 / 0 (98 reused) | 64 / 100 | 64.0 % (54.2 %–72.7 %) | 0.3995 | 0.3249 | 31.6 | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | `als_cf` | 28 | 64 | +36 | 41 | 5 | 0.0 |
| en | sampled | `popularity` | 34 | 64 | +30 | 44 | 14 | 0.0 |
| cs | sampled | `als_cf` | 28 | 64 | +36 | 40 | 4 | 0.0 |
| cs | sampled | `popularity` | 34 | 64 | +30 | 45 | 15 | 0.0 |

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
