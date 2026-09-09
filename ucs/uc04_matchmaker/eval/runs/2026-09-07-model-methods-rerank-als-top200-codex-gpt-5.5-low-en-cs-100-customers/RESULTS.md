# UC-04 model methods — 2026-09-07-model-methods-rerank-als-top200-codex-gpt-5.5-low-en-cs-100-customers

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 100 customers; the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: codex / gpt-5.5 / low (CLI codex-cli 0.153.4)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 38 s, 88 model calls (85 reused from `2026-09-07-model-methods-1-methods-codex-gpt-5.5-low-en-cs-100-customers-3`)
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model re-ranks the ALS top 200 (full catalogue) (`rerank_als_top200`)

    en full: 11/44 hits@10, HR 25.0 %   (95 % CI 14.6 %–39.4 %; NDCG@10 0.143; calls 5 / 39 / 0 (42 reused); vs `als_cf` 6 → 11 (+5; only method 6, only als_cf 1; sign p 0.125))
    cs full: 10/44 hits@10, HR 22.7 %   (95 % CI 12.8 %–37.0 %; NDCG@10 0.129; calls 5 / 39 / 0 (43 reused); hidden item among the dropped ids 1×; vs `als_cf` 6 → 10 (+4; only method 6, only als_cf 2; sign p 0.289))

In the en branch: `rerank_als_top200` 11 of 44 against ALS's 6 under `full` (+5, sign p 0.125). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
