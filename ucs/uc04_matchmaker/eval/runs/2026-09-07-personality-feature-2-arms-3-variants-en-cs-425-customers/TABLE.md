# Personality feature: 2026-09-07-personality-feature-2-arms-3-variants-en-cs-425-customers

## LightGBM on engineered features, protocol full (hits in the top 10 of 425; guessing 0.2)

| variant | en hits (95 % CI of HR@10) | cs hits (95 % CI of HR@10) |
| --- | --- | --- |
| none | 2 (0.1–1.7 %) | 2 (0.1–1.7 %) |
| inferred | 1 (0.0–1.3 %) | 1 (0.0–1.3 %) |
| sampled | 2 (0.1–1.7 %) | 2 (0.1–1.7 %) |

## LightGBM on engineered features, protocol sampled (hits in the top 10 of 425; guessing 42.1)

| variant | en hits (95 % CI of HR@10) | cs hits (95 % CI of HR@10) |
| --- | --- | --- |
| none | 151 (31.1–40.2 %) | 151 (31.1–40.2 %) |
| inferred | 152 (31.4–40.4 %) | 152 (31.4–40.4 %) |
| sampled | 151 (31.1–40.2 %) | 151 (31.1–40.2 %) |

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
| lightgbm_features | en | full | inferred vs none | 425 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| lightgbm_features | en | full | sampled vs none | 271 | 2 vs 2 | +0 | 1 / 1 | 1.0 |
| lightgbm_features | en | full | inferred vs sampled | 271 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| lightgbm_features | en | sampled | inferred vs none | 425 | 152 vs 151 | +1 | 23 / 22 | 1.0 |
| lightgbm_features | en | sampled | sampled vs none | 271 | 96 vs 99 | -3 | 13 / 16 | 0.711 |
| lightgbm_features | en | sampled | inferred vs sampled | 271 | 100 vs 96 | +4 | 15 / 11 | 0.557 |
| lightgbm_features | cs | full | inferred vs none | 425 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| lightgbm_features | cs | full | sampled vs none | 271 | 2 vs 2 | +0 | 1 / 1 | 1.0 |
| lightgbm_features | cs | full | inferred vs sampled | 271 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| lightgbm_features | cs | sampled | inferred vs none | 425 | 152 vs 151 | +1 | 23 / 22 | 1.0 |
| lightgbm_features | cs | sampled | sampled vs none | 271 | 96 vs 99 | -3 | 13 / 16 | 0.711 |
| lightgbm_features | cs | sampled | inferred vs sampled | 271 | 100 vs 96 | +4 | 15 / 11 | 0.557 |
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
