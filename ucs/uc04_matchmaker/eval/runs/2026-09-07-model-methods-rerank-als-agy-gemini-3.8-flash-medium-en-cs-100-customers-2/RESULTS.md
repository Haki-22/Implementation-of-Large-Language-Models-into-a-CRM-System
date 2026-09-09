# UC-04 model methods — 2026-09-07-model-methods-rerank-als-agy-gemini-3.8-flash-medium-en-cs-100-customers-2

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 100 customers; the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: agy / gemini-3.8-flash / medium (CLI 1.1.27)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 39 s, 200 model calls (199 reused from `2026-09-07-model-methods-rerank-als-agy-gemini-3.8-flash-medium-en-cs-100-customers`)
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model re-ranks the ALS order (`rerank_als`)

    en sampled: 58/100 hits@10, HR 58.0 %   (95 % CI 48.2 %–67.2 %; NDCG@10 0.379; calls 91 / 9 / 0 (99 reused); hidden item among the dropped ids 1×; vs `als_cf` 28 → 58 (+30; only method 33, only als_cf 3; sign p 0.0))
    cs sampled: 56/100 hits@10, HR 56.0 %   (95 % CI 46.2 %–65.3 %; NDCG@10 0.371; calls 95 / 5 / 0 (100 reused); vs `als_cf` 28 → 56 (+28; only method 30, only als_cf 2; sign p 0.0))

In the en branch: `rerank_als` 58 of 100 against ALS's 28 under `sampled` (+30, sign p 0.0). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
