# UC-04 model methods — 2026-09-07-model-methods-describe-and-retrieve-agy-gemini-3.8-flash-medium-en-cs-100-customers

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 100 customers; the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: agy / gemini-3.8-flash / medium (CLI 1.1.27)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 37 s, 200 model calls (197 reused from `2026-09-07-model-methods-2-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers`)
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model describes the next purchase, the catalogue index retrieves it (`describe_and_retrieve`)

    en full: 2/100 hits@10, HR 2.0 %        (95 % CI 0.6 %–7.0 %; NDCG@10 0.006; calls 100 / 0 / 0 (97 reused); vs `als_cf` 3 → 2 (-1; only method 2, only als_cf 3; sign p 1.0); vs `popularity` 0 → 2 (+2; only method 2, only popularity 0; sign p 0.5))
    en sampled: 25/100 hits@10, HR 25.0 %   (95 % CI 17.5 %–34.3 %; NDCG@10 0.148; calls 100 / 0 / 0 (97 reused); vs `als_cf` 28 → 25 (-3; only method 17, only als_cf 20; sign p 0.743); vs `popularity` 34 → 25 (-9; only method 19, only popularity 28; sign p 0.243))
    cs full: 3/100 hits@10, HR 3.0 %        (95 % CI 1.0 %–8.5 %; NDCG@10 0.016; calls 100 / 0 / 0 (100 reused); vs `als_cf` 3 → 3 (0; only method 3, only als_cf 3; sign p 1.0); vs `popularity` 0 → 3 (+3; only method 3, only popularity 0; sign p 0.25))
    cs sampled: 21/100 hits@10, HR 21.0 %   (95 % CI 14.2 %–30.0 %; NDCG@10 0.123; calls 100 / 0 / 0 (100 reused); vs `als_cf` 28 → 21 (-7; only method 16, only als_cf 23; sign p 0.337); vs `popularity` 34 → 21 (-13; only method 15, only popularity 28; sign p 0.066))

In the en branch: `describe_and_retrieve` 2 of 100 against ALS's 3 under `full` (-1, sign p 1.0); `describe_and_retrieve` 25 of 100 against ALS's 28 under `sampled` (-3, sign p 0.743). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
