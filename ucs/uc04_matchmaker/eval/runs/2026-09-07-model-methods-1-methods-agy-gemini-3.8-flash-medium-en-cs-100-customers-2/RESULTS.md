# UC-04 model methods — 2026-09-07-model-methods-1-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers-2

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 100 customers; the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: agy / gemini-3.8-flash / medium (CLI 1.1.27)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 37 s, 200 model calls (198 reused from `2026-09-07-model-methods-1-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers`)
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model ranks the candidates alone (`rank_candidates`)

    en sampled: 64/100 hits@10, HR 64.0 %   (95 % CI 54.2 %–72.7 %; NDCG@10 0.383; calls 94 / 6 / 0 (100 reused); vs `als_cf` 28 → 64 (+36; only method 41, only als_cf 5; sign p 0.0); vs `popularity` 34 → 64 (+30; only method 44, only popularity 14; sign p 0.0))
    cs sampled: 64/100 hits@10, HR 64.0 %   (95 % CI 54.2 %–72.7 %; NDCG@10 0.399; calls 90 / 10 / 0 (98 reused); vs `als_cf` 28 → 64 (+36; only method 40, only als_cf 4; sign p 0.0); vs `popularity` 34 → 64 (+30; only method 45, only popularity 15; sign p 0.0))

In the en branch: `rank_candidates` 64 of 100 against ALS's 28 under `sampled` (+36, sign p 0.0). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
