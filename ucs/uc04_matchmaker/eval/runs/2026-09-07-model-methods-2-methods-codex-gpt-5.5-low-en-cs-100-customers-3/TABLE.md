# UC-04 model methods — 2026-09-07-model-methods-2-methods-codex-gpt-5.5-low-en-cs-100-customers-3

Sample `model-arms-100`: 100 customers; provider codex / gpt-5.5 / low (CLI codex-cli 0.153.4); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). 'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right answer, which then lands at the end of the list.

## `rerank_als` — Model re-ranks the ALS order

whole history + the 101 sampled candidates in ALS order with their scores; the model may move a candidate only where the history supports it. ML input: ALS order and scores of the 101 sampled candidates.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | 100 | 49 / 51 / 0 (100 reused); hidden item among the dropped ids 1× | 57 / 100 | 57.0 % (47.2 %–66.3 %) | 0.3941 | 0.3386 | — | 28 / 100 | 34 / 100 |
| cs | sampled | 100 | 58 / 42 / 0 (100 reused) | 54 / 100 | 54.0 % (44.3 %–63.4 %) | 0.3732 | 0.3212 | — | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | `als_cf` | 28 | 57 | +29 | 32 | 3 | 0.0 |
| cs | sampled | `als_cf` | 28 | 54 | +26 | 28 | 2 | 0.0 |

## `rerank_als_with_profile` — Model re-ranks the ALS order with the customer profile

method 3 plus the profile from the CRM: Big Five estimate, lifecycle stage, interest topics, persona and aspects where present; the profile breaks ties only. ML input: ALS order and scores of the 101 sampled candidates; the profile from the database.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | 100 | 50 / 50 / 0 (99 reused) | 51 / 100 | 51.0 % (41.3 %–60.6 %) | 0.3380 | 0.2853 | 9.0 | 28 / 100 | 34 / 100 |
| cs | sampled | 100 | 49 / 51 / 0 (100 reused) | 48 / 100 | 48.0 % (38.5 %–57.7 %) | 0.3469 | 0.3048 | — | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | `als_cf` | 28 | 51 | +23 | 28 | 5 | 0.0 |
| en | sampled | `rerank_als` | 57 | 51 | -6 | 3 | 9 | 0.146 |
| cs | sampled | `als_cf` | 28 | 48 | +20 | 24 | 4 | 0.0 |
| cs | sampled | `rerank_als` | 54 | 48 | -6 | 2 | 8 | 0.109 |

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
