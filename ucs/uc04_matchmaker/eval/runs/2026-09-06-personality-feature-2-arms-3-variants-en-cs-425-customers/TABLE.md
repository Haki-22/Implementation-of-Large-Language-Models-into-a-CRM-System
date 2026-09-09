# Personality feature: 2026-09-06-personality-feature-2-arms-3-variants-en-cs-425-customers

## LightGBM on engineered features, protocol full (hits in the top 10 of 425; guessing 0.2)

| variant | en hits (95 % CI of HR@10) | cs hits (95 % CI of HR@10) |
| --- | --- | --- |
| none | 1 (0.0–1.3 %) | 1 (0.0–1.3 %) |
| inferred | 0 (0.0–0.9 %) | 0 (0.0–0.9 %) |
| sampled | 4 (0.4–2.4 %) | 4 (0.4–2.4 %) |

## LightGBM on engineered features, protocol sampled (hits in the top 10 of 425; guessing 42.1)

| variant | en hits (95 % CI of HR@10) | cs hits (95 % CI of HR@10) |
| --- | --- | --- |
| none | 149 (30.7–39.7 %) | 149 (30.7–39.7 %) |
| inferred | 155 (32.0–41.1 %) | 155 (32.0–41.1 %) |
| sampled | 152 (31.4–40.4 %) | 152 (31.4–40.4 %) |

## Linear SVM on engineered features, protocol full (hits in the top 10 of 425; guessing 0.2)

| variant | en hits (95 % CI of HR@10) | cs hits (95 % CI of HR@10) |
| --- | --- | --- |
| none | 1 (0.0–1.3 %) | 1 (0.0–1.3 %) |
| inferred | 1 (0.0–1.3 %) | 1 (0.0–1.3 %) |
| sampled | 1 (0.0–1.3 %) | 1 (0.0–1.3 %) |

## Linear SVM on engineered features, protocol sampled (hits in the top 10 of 425; guessing 42.1)

| variant | en hits (95 % CI of HR@10) | cs hits (95 % CI of HR@10) |
| --- | --- | --- |
| none | 65 (12.2–19.0 %) | 65 (12.2–19.0 %) |
| inferred | 65 (12.2–19.0 %) | 65 (12.2–19.0 %) |
| sampled | 65 (12.2–19.0 %) | 65 (12.2–19.0 %) |

## Paired differences (hit = hidden item in the top 10 under a variant)

| arm | branch | protocol | pair | n | hits | difference | discordant (first / second) | sign test p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm_features | en | full | inferred vs none | 425 | 0 vs 1 | -1 | 0 / 1 | 1.0 |
| lightgbm_features | en | full | sampled vs none | 271 | 4 vs 1 | +3 | 3 / 0 | 0.25 |
| lightgbm_features | en | full | inferred vs sampled | 271 | 0 vs 4 | -4 | 0 / 4 | 0.125 |
| lightgbm_features | en | sampled | inferred vs none | 425 | 155 vs 149 | +6 | 15 / 9 | 0.307 |
| lightgbm_features | en | sampled | sampled vs none | 271 | 98 vs 95 | +3 | 14 / 11 | 0.69 |
| lightgbm_features | en | sampled | inferred vs sampled | 271 | 101 vs 98 | +3 | 17 / 14 | 0.72 |
| lightgbm_features | cs | full | inferred vs none | 425 | 0 vs 1 | -1 | 0 / 1 | 1.0 |
| lightgbm_features | cs | full | sampled vs none | 271 | 4 vs 1 | +3 | 3 / 0 | 0.25 |
| lightgbm_features | cs | full | inferred vs sampled | 271 | 0 vs 4 | -4 | 0 / 4 | 0.125 |
| lightgbm_features | cs | sampled | inferred vs none | 425 | 155 vs 149 | +6 | 15 / 9 | 0.307 |
| lightgbm_features | cs | sampled | sampled vs none | 271 | 98 vs 95 | +3 | 14 / 11 | 0.69 |
| lightgbm_features | cs | sampled | inferred vs sampled | 271 | 101 vs 98 | +3 | 17 / 14 | 0.72 |
| svm_features | en | full | inferred vs none | 425 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| svm_features | en | full | sampled vs none | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| svm_features | en | full | inferred vs sampled | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| svm_features | en | sampled | inferred vs none | 425 | 65 vs 65 | +0 | 0 / 0 | 1.0 |
| svm_features | en | sampled | sampled vs none | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
| svm_features | en | sampled | inferred vs sampled | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
| svm_features | cs | full | inferred vs none | 425 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| svm_features | cs | full | sampled vs none | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| svm_features | cs | full | inferred vs sampled | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| svm_features | cs | sampled | inferred vs none | 425 | 65 vs 65 | +0 | 0 / 0 | 1.0 |
| svm_features | cs | sampled | sampled vs none | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
| svm_features | cs | sampled | inferred vs sampled | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
