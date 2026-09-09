# UC-04 model methods — 2026-09-07-model-methods-rank-candidates-describe-and-retrieve-codex-gpt-5.6-terra-low-en-cs-100-customers-3

Ran on: `substrate.db` (sha256 d259e9c85568…), 425 linked customers, 18213 products
Who: sample `model-arms-100`, 100 customers; the top-200 method on the customers whose hidden item ALS placed within its top 200
Provider / model / tier: codex / gpt-5.6-terra / low (CLI codex-cli 0.153.4)
Prompts: version 1.0.2; English branch in English, Czech branch in Czech
Protocols: sampled (1 hidden + 100 unbought, guessing 9.9 %) and full (the whole catalogue, guessing 0.1 %); seed 42
When: 2026-09-07, 41 s, 400 model calls (396 reused from `2026-09-07-model-methods-rank-candidates-describe-and-retrieve-codex-gpt-5.6-terra-low-en-cs-100-customers-2`)
Czech branch: Czech instruction and Czech product titles (16 067 of 18 213; English title otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, design §8.1)

## Model ranks the candidates alone (`rank_candidates`)

    en sampled: 46/100 hits@10, HR 46.0 %   (95 % CI 36.6 %–55.7 %; NDCG@10 0.308; calls 46 / 54 / 0 (99 reused); vs `als_cf` 28 → 46 (+18; only method 28, only als_cf 10; sign p 0.005); vs `popularity` 34 → 46 (+12; only method 32, only popularity 20; sign p 0.126))
    cs sampled: 45/100 hits@10, HR 45.0 %   (95 % CI 35.6 %–54.8 %; NDCG@10 0.295; calls 48 / 52 / 0 (97 reused); vs `als_cf` 28 → 45 (+17; only method 28, only als_cf 11; sign p 0.009); vs `popularity` 34 → 45 (+11; only method 31, only popularity 20; sign p 0.161))

## Model describes the next purchase, the catalogue index retrieves it (`describe_and_retrieve`)

    en full: 0/100 hits@10, HR 0.0 %        (95 % CI 0.0 %–3.7 %; NDCG@10 0.000; calls 100 / 0 / 0 (100 reused); vs `als_cf` 3 → 0 (-3; only method 0, only als_cf 3; sign p 0.25); vs `popularity` 0 → 0 (0; only method 0, only popularity 0; sign p 1.0))
    en sampled: 29/100 hits@10, HR 29.0 %   (95 % CI 21.0 %–38.5 %; NDCG@10 0.170; calls 100 / 0 / 0 (100 reused); vs `als_cf` 28 → 29 (+1; only method 16, only als_cf 15; sign p 1.0); vs `popularity` 34 → 29 (-5; only method 21, only popularity 26; sign p 0.56))
    cs full: 0/100 hits@10, HR 0.0 %        (95 % CI 0.0 %–3.7 %; NDCG@10 0.000; calls 100 / 0 / 0 (100 reused); vs `als_cf` 3 → 0 (-3; only method 0, only als_cf 3; sign p 0.25); vs `popularity` 0 → 0 (0; only method 0, only popularity 0; sign p 1.0))
    cs sampled: 27/100 hits@10, HR 27.0 %   (95 % CI 19.3 %–36.4 %; NDCG@10 0.168; calls 100 / 0 / 0 (100 reused); vs `als_cf` 28 → 27 (-1; only method 16, only als_cf 17; sign p 1.0); vs `popularity` 34 → 27 (-7; only method 20, only popularity 27; sign p 0.382))

In the en branch: `rank_candidates` 46 of 100 against ALS's 28 under `sampled` (+18, sign p 0.005); `describe_and_retrieve` 0 of 100 against ALS's 3 under `full` (-3, sign p 0.25); `describe_and_retrieve` 29 of 100 against ALS's 28 under `sampled` (+1, sign p 1.0). A difference whose sign test does not reach 0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax.
