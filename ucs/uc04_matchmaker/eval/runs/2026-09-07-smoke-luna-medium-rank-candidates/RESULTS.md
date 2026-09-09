# UC-04 model methods — 2026-09-07-smoke-luna-medium-rank-candidates

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 5 customers (limit 5); the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: codex / gpt-5.6-luna / medium (CLI codex-cli 0.153.4)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 1 min 27 s, 10 model calls
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model ranks the candidates alone (`rank_candidates`)

    en sampled: 1/5 hits@10, HR 20.0 %   (95 % CI 3.6 %–62.4 %; NDCG@10 0.077; calls 1 / 1 / 3; vs `als_cf` 2 → 1 (-1; only method 1, only als_cf 2; sign p 1.0); vs `popularity` 2 → 1 (-1; only method 1, only popularity 2; sign p 1.0))
    cs sampled: 2/5 hits@10, HR 40.0 %   (95 % CI 11.8 %–76.9 %; NDCG@10 0.149; calls 3 / 0 / 2; vs `als_cf` 2 → 2 (0; only method 1, only als_cf 1; sign p 1.0); vs `popularity` 2 → 2 (0; only method 1, only popularity 1; sign p 1.0))

In the en branch: `rank_candidates` 1 of 5 against ALS's 2 under `sampled` (-1, sign p 1.0). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
