# UC-04 model methods — 2026-09-07-model-methods-2-methods-codex-gpt-5.5-low-en-cs-100-customers-3

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 100 customers; the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: codex / gpt-5.5 / low (CLI codex-cli 0.153.4)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 11 s, 400 model calls (399 reused from `2026-09-07-model-methods-2-methods-codex-gpt-5.5-low-en-cs-100-customers-2`)
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model re-ranks the ALS order (`rerank_als`)

    en sampled: 57/100 hits@10, HR 57.0 %   (95 % CI 47.2 %–66.3 %; NDCG@10 0.394; calls 49 / 51 / 0 (100 reused); hidden item among the dropped ids 1×; vs `als_cf` 28 → 57 (+29; only method 32, only als_cf 3; sign p 0.0))
    cs sampled: 54/100 hits@10, HR 54.0 %   (95 % CI 44.3 %–63.4 %; NDCG@10 0.373; calls 58 / 42 / 0 (100 reused); vs `als_cf` 28 → 54 (+26; only method 28, only als_cf 2; sign p 0.0))

## Model re-ranks the ALS order with the customer profile (`rerank_als_with_profile`)

    en sampled: 51/100 hits@10, HR 51.0 %   (95 % CI 41.3 %–60.6 %; NDCG@10 0.338; calls 50 / 50 / 0 (99 reused); vs `als_cf` 28 → 51 (+23; only method 28, only als_cf 5; sign p 0.0); vs `rerank_als` 57 → 51 (-6; only method 3, only rerank_als 9; sign p 0.146))
    cs sampled: 48/100 hits@10, HR 48.0 %   (95 % CI 38.5 %–57.7 %; NDCG@10 0.347; calls 49 / 51 / 0 (100 reused); vs `als_cf` 28 → 48 (+20; only method 24, only als_cf 4; sign p 0.0); vs `rerank_als` 54 → 48 (-6; only method 2, only rerank_als 8; sign p 0.109))

In the en branch: `rerank_als` 57 of 100 against ALS's 28 under `sampled` (+29, sign p 0.0); `rerank_als_with_profile` 51 of 100 against ALS's 28 under `sampled` (+23, sign p 0.0). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
