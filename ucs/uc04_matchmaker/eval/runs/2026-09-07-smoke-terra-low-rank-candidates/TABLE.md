# UC-04 model methods — 2026-09-07-smoke-terra-low-rank-candidates

Sample `model-arms-100`: 5 customers (limit 5); provider codex / gpt-5.6-terra / low (CLI codex-cli 0.153.4); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). 'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right answer, which then lands at the end of the list.

## `rank_candidates` — Model ranks the candidates alone

whole history + the 101 sampled candidates in a seeded random order; the model returns the full permutation; no classical input. ML input: none.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | 5 | 1 / 4 / 0 | 3 / 5 | 60.0 % (23.1 %–88.2 %) | 0.3297 | 0.2400 | 11.7 | 2 / 5 | 2 / 5 |
| cs | sampled | 5 | 3 / 2 / 0 | 3 / 5 | 60.0 % (23.1 %–88.2 %) | 0.3297 | 0.2400 | 12.2 | 2 / 5 | 2 / 5 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | `als_cf` | 2 | 3 | +1 | 2 | 1 | 1.0 |
| en | sampled | `popularity` | 2 | 3 | +1 | 2 | 1 | 1.0 |
| cs | sampled | `als_cf` | 2 | 3 | +1 | 2 | 1 | 1.0 |
| cs | sampled | `popularity` | 2 | 3 | +1 | 2 | 1 | 1.0 |

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
