# UC-04 results — customer × product matchmaker, classical machine learning against language models

Ran on: `substrate.db` (the database was rebuilt between the runs (same customers, histories and hidden items; a rebuild changed the profile columns or the message briefs, which no arm reads): `2026-09-07-arena-crm-population-12-arms-en-cs-425-customers` on aba47a161d87…; `2026-09-07-personality-feature-2-arms-3-variants-en-cs-425-customers` on aba47a161d87…; `2026-09-07-outputs-for-uc01-codex-gpt-5.6-luna-low-16-contacts` on d259e9c85568…; `2026-09-07-model-methods-1-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers-2` on aba47a161d87…; `2026-09-07-model-methods-2-methods-codex-gpt-5.5-low-en-cs-100-customers-3` on aba47a161d87…; `2026-09-07-model-methods-describe-and-retrieve-agy-gemini-3.8-flash-medium-en-cs-100-customers` on aba47a161d87…; `2026-09-07-model-methods-rerank-als-top200-codex-gpt-5.5-low-en-cs-100-customers` on aba47a161d87…; `2026-09-07-model-methods-rerank-als-agy-gemini-3.8-flash-medium-en-cs-100-customers-2` on aba47a161d87…; `2026-09-07-model-methods-rank-candidates-describe-and-retrieve-codex-gpt-5.6-terra-low-en-cs-100-customers-3` on d259e9c85568…), 425 linked customers with the chronologically last purchase hidden, 18213 products. Two protocols (the hidden item against the whole catalogue, and against 100 sampled unbought products), two branches (English, Czech), regimes CRM and population for the collaborative arms. Every number below sits in a run folder under `eval/runs/` with its `config.json` (database hash, seeds, package versions, the full prompts of the model methods) and its own card. Generated 2026-09-07 by `python -m ucs.uc04_matchmaker card`.

## 1. The data behind the numbers — `runs/2026-09-07-data-facts-425-customers-population/`

    425 customers, 18213 products                               (density 0.588 %; 10355 of the 18116 products ever bought have one buyer)
    108 hidden items bought by nobody else                      (no collaborative method can reach them; the ceiling of the full protocol)
    history 94 products median (11–430)                         (heavy buyers; the whole history fits a model prompt)
    Czech titles for 16067 products, 3181 history texts empty   (what the Czech branch reads)
    population 192403 users / 1689188 reviews                   (the public dump the population regime learns from)

## 2. Classical arms — `runs/2026-09-07-arena-crm-population-12-arms-en-cs-425-customers/`

Twelve arms, both branches, both protocols, regimes CRM and population, 425 customers; guessing scores 0.1 % at top 10 against the whole catalogue and 9.9 % against 100 sampled negatives.

    crm / full: best `hybrid_als_dense` 8 of 425                                                         (en; cs 7; 95 % CI 1.0 %–3.7 %)
    crm / sampled: best `adamic_adar` 154 of 425                                                         (en; cs 154; 95 % CI 31.8 %–40.9 %)
    population / sampled: best `als_cf` 182 of 425                                                       (en; cs 182; 95 % CI 38.2 %–47.6 %)
    ALS sampled: CRM 119 → population 182                                                                (learning from the public dump lifts collaborative filtering)
    Czech tax: bert_encoder 94 → 46, bm25_text 57 → 75, dense_e5 131 → 110, hybrid_als_dense 148 → 128   (arms that read text, en → cs, sampled; arms that read none score identically)

## 3. The personality column — `runs/2026-09-07-personality-feature-2-arms-3-variants-en-cs-425-customers/`

    lightgbm_features: inferred profile +1 of 425   (151 → 152 hits, discordant 23/22, sign p 1.0)
    lightgbm_features: sampled profile -3 of 271    (99 → 96 hits, discordant 13/16, sign p 0.711)
    svm_features: inferred profile 0 of 425         (65 → 65 hits, discordant 0/0, sign p 1.0)
    svm_features: sampled profile 0 of 271          (44 → 44 hits, discordant 0/0, sign p 1.0)

## 4. The outputs for UC-01 — `runs/2026-09-07-outputs-for-uc01-codex-gpt-5.6-luna-low-16-contacts/`

    80 of 80 reasons grounded                      (every cited purchase exists in the history shown; 18.0 words median)
    16 personas, 74 of 75 aspect quotes verbatim   (checked, not trusted)
    112 calls, codex / gpt-5.6-luna / low          (prompt 1.0.1; topics + lifecycle for 425 contacts)

## 5. The model methods — one record folder per method

`runs/2026-09-07-model-methods-1-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers-2/` — rank_candidates: agy / gemini-3.8-flash / medium, prompt 1.0.2
`runs/2026-09-07-model-methods-2-methods-codex-gpt-5.5-low-en-cs-100-customers-3/` — rerank_als, rerank_als_with_profile: codex / gpt-5.5 / low, prompt 1.0.2
`runs/2026-09-07-model-methods-describe-and-retrieve-agy-gemini-3.8-flash-medium-en-cs-100-customers/` — describe_and_retrieve: agy / gemini-3.8-flash / medium, prompt 1.0.2
`runs/2026-09-07-model-methods-rerank-als-top200-codex-gpt-5.5-low-en-cs-100-customers/` — rerank_als_top200: codex / gpt-5.5 / low, prompt 1.0.2

    rank_candidates (sampled): 64 of 100           (cs 64; ALS 28 on the same lists (+36, sign p 0.0); calls ok/partial/failed 94/6/0)
    rerank_als (sampled): 57 of 100                (cs 54; ALS 28 on the same lists (+29, sign p 0.0); calls ok/partial/failed 49/51/0)
    rerank_als_with_profile (sampled): 51 of 100   (cs 48; ALS 28 on the same lists (+23, sign p 0.0); calls ok/partial/failed 50/50/0)
    describe_and_retrieve (full): 2 of 100         (cs 3; ALS 3 on the same lists (-1, sign p 1.0); calls ok/partial/failed 100/0/0)
    describe_and_retrieve (sampled): 25 of 100     (cs 21; ALS 28 on the same lists (-3, sign p 0.743); calls ok/partial/failed 100/0/0)
    rerank_als_top200 (full): 11 of 44             (cs 10; ALS 6 on the same lists (+5, sign p 0.125); calls ok/partial/failed 5/39/0)
    profile vs plain re-rank: en -6, cs -6         (sign p 0.146 / 0.109; the CRM profile in the prompt does not help)

## 6. The same method on a second provider — comparison folders, never the record

`runs/2026-09-07-model-methods-rerank-als-agy-gemini-3.8-flash-medium-en-cs-100-customers-2/` — rerank_als: agy / gemini-3.8-flash / medium, prompt 1.0.2
    rerank_als (sampled): en 58 / cs 56 of 100              (record codex / gpt-5.5 / low: 57 / 54; calls ok/partial/failed 91/9/0)

`runs/2026-09-07-model-methods-rank-candidates-describe-and-retrieve-codex-gpt-5.6-terra-low-en-cs-100-customers-3/` — rank_candidates, describe_and_retrieve: codex / gpt-5.6-terra / low, prompt 1.0.2
    rank_candidates (sampled): en 46 / cs 45 of 100         (record agy / gemini-3.8-flash / medium: 64 / 64; calls ok/partial/failed 46/54/0)
    describe_and_retrieve (full): en 0 / cs 0 of 100        (record agy / gemini-3.8-flash / medium: 2 / 3; calls ok/partial/failed 100/0/0)
    describe_and_retrieve (sampled): en 29 / cs 27 of 100   (record agy / gemini-3.8-flash / medium: 25 / 21; calls ok/partial/failed 100/0/0)

Reading: on the sampled lists the model re-ranking ALS scores 57 of 100 against ALS's 28 and the model alone 64: a strong complement, and on lists of 101 products from random categories stronger alone; against the whole catalogue the only method that moves the number is the re-rank of ALS's top 200 (6 → 11 of 44), at the edge of significance. The profile of the customer, as a column in the classical arms or as text in the prompt, adds nothing measurable.

Appendix files generated from the same folders: `attachments/uc04-arena-results.{csv,md}`, `uc04-data-facts.{csv,md}`, `uc04-personality-feature.{csv,md}`, `uc04-outputs-for-uc01.{csv,md}`, `uc04-model-methods.{csv,md}`, `uc04-arms.md`.
