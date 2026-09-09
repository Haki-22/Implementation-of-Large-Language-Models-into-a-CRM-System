# UC-04 model methods — 2026-09-07-model-methods-rerank-als-top200-codex-gpt-5.5-low-en-cs-100-customers

Sample `model-arms-100`: 100 customers; provider codex / gpt-5.5 / low (CLI codex-cli 0.153.4); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). 'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right answer, which then lands at the end of the list.

## `rerank_als_top200` — Model re-ranks the ALS top 200 (full catalogue)

for the customers whose hidden item ALS placed within its top 200: those 200 in ALS order with scores, the model re-orders them; the honest test against the whole catalogue. ML input: ALS top 200 of the whole catalogue, with scores.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | full | 44 | 5 / 39 / 0 (42 reused) | 11 / 44 | 25.0 % (14.6 %–39.4 %) | 0.1431 | 0.1109 | 17.7 | 6 / 44 | 0 / 44 |
| cs | full | 44 | 5 / 39 / 0 (43 reused); hidden item among the dropped ids 1× | 10 / 44 | 22.7 % (12.8 %–37.0 %) | 0.1294 | 0.1000 | 15.2 | 6 / 44 | 0 / 44 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | full | `als_cf` | 6 | 11 | +5 | 6 | 1 | 0.125 |
| cs | full | `als_cf` | 6 | 10 | +4 | 6 | 2 | 0.289 |

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
