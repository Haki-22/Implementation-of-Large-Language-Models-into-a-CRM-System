# UC-04 model methods — 2026-09-07-model-methods-rerank-als-agy-gemini-3.8-flash-medium-en-cs-100-customers-2

Sample `model-arms-100`: 100 customers; provider agy / gemini-3.8-flash / medium (CLI 1.1.27); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). 'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right answer, which then lands at the end of the list.

## `rerank_als` — Model re-ranks the ALS order

whole history + the 101 sampled candidates in ALS order with their scores; the model may move a candidate only where the history supports it. ML input: ALS order and scores of the 101 sampled candidates.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | 100 | 91 / 9 / 0 (99 reused); hidden item among the dropped ids 1× | 58 / 100 | 58.0 % (48.2 %–67.2 %) | 0.3788 | 0.3167 | 36.6 | 28 / 100 | 34 / 100 |
| cs | sampled | 100 | 95 / 5 / 0 (100 reused) | 56 / 100 | 56.0 % (46.2 %–65.3 %) | 0.3712 | 0.3140 | — | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | `als_cf` | 28 | 58 | +30 | 33 | 3 | 0.0 |
| cs | sampled | `als_cf` | 28 | 56 | +28 | 30 | 2 | 0.0 |

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
