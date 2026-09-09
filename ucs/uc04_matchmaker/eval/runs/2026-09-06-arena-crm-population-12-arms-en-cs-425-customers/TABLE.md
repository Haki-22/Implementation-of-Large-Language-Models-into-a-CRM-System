# UC-04 arena — 2026-09-06-arena-crm-population-12-arms-en-cs-425-customers

Customers 425 (groups {'A': 300, 'B': 50, 'C': 75}), catalogue 18213 products, seed 42. Full protocol: the hidden last purchase ranked against the whole catalogue, guessing scores 0.1 % at top 10. Sampled protocol: ranked against 100 random unbought products, the same list for every arm, guessing scores 9.9 %. The sampled protocol is an easier task and its numbers are not comparable with the full one; it is the protocol of the recommender literature.

## Regime `crm` · protocol `full`

| arm | what it does | en: hits / n | en: HR@10 (95 % CI) | en: NDCG@10 | cs: hits / n | cs: HR@10 (95 % CI) | cs: NDCG@10 | en: hidden in top 30 / 200 | cs: hidden in top 30 / 200 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `popularity` | Most-bought products | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0009 | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0009 | 5 / 33 | 5 / 33 |
| `als_cf` | ALS collaborative filtering | 6 / 425 | 1.4 % (0.6 %–3.0 %) | 0.0056 | 6 / 425 | 1.4 % (0.6 %–3.0 %) | 0.0056 | 12 / 45 | 12 / 45 |
| `svd_mf` | SVD matrix factorisation | 6 / 425 | 1.4 % (0.6 %–3.0 %) | 0.0079 | 6 / 425 | 1.4 % (0.6 %–3.0 %) | 0.0079 | 16 / 48 | 16 / 48 |
| `apriori_rules` | Apriori association rules | 5 / 425 | 1.2 % (0.5 %–2.7 %) | 0.0048 | 5 / 425 | 1.2 % (0.5 %–2.7 %) | 0.0048 | 14 / 48 | 14 / 48 |
| `adamic_adar` | Adamic-Adar link prediction | 3 / 425 | 0.7 % (0.2 %–2.1 %) | 0.0025 | 3 / 425 | 0.7 % (0.2 %–2.1 %) | 0.0025 | 10 / 53 | 10 / 53 |
| `naive_bayes` | Naive Bayes over the purchase history | 4 / 425 | 0.9 % (0.4 %–2.4 %) | 0.0039 | 4 / 425 | 0.9 % (0.4 %–2.4 %) | 0.0039 | 10 / 40 | 10 / 40 |
| `bm25_text` | BM25 keyword search | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0012 | 2 / 425 | 0.5 % (0.1 %–1.7 %) | 0.0023 | 2 / 13 | 4 / 14 |
| `dense_e5` | Dense multilingual retrieval (e5) | 4 / 425 | 0.9 % (0.4 %–2.4 %) | 0.0037 | 2 / 425 | 0.5 % (0.1 %–1.7 %) | 0.0015 | 7 / 26 | 4 / 20 |
| `bert_encoder` | BERT encoders as recommenders | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0008 | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0007 | 2 / 19 | 1 / 4 |
| `hybrid_als_dense` | ALS + dense hybrid | 8 / 425 | 1.9 % (1.0 %–3.7 %) | 0.0083 | 7 / 425 | 1.6 % (0.8 %–3.4 %) | 0.0084 | 19 / 36 | 13 / 35 |
| `lightgbm_features` | LightGBM on engineered features | 2 / 425 | 0.5 % (0.1 %–1.7 %) | 0.0023 | 2 / 425 | 0.5 % (0.1 %–1.7 %) | 0.0023 | 5 / 29 | 5 / 29 |
| `svm_features` | Linear SVM on engineered features | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0007 | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0007 | 3 / 12 | 3 / 12 |
| _guessing_ | random top 10 | — | 0.1 % | — | — | 0.1 % | — | — | — |

## Regime `crm` · protocol `sampled`

| arm | what it does | en: hits / n | en: HR@10 (95 % CI) | en: NDCG@10 | cs: hits / n | cs: HR@10 (95 % CI) | cs: NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `popularity` | Most-bought products | 125 / 425 | 29.4 % (25.3 %–33.9 %) | 0.1647 | 125 / 425 | 29.4 % (25.3 %–33.9 %) | 0.1647 |
| `als_cf` | ALS collaborative filtering | 119 / 425 | 28.0 % (23.9 %–32.5 %) | 0.1672 | 119 / 425 | 28.0 % (23.9 %–32.5 %) | 0.1672 |
| `svd_mf` | SVD matrix factorisation | 125 / 425 | 29.4 % (25.3 %–33.9 %) | 0.1836 | 125 / 425 | 29.4 % (25.3 %–33.9 %) | 0.1836 |
| `apriori_rules` | Apriori association rules | 110 / 425 | 25.9 % (21.9 %–30.2 %) | 0.1710 | 110 / 425 | 25.9 % (21.9 %–30.2 %) | 0.1710 |
| `adamic_adar` | Adamic-Adar link prediction | 154 / 425 | 36.2 % (31.8 %–40.9 %) | 0.2192 | 154 / 425 | 36.2 % (31.8 %–40.9 %) | 0.2192 |
| `naive_bayes` | Naive Bayes over the purchase history | 91 / 425 | 21.4 % (17.8 %–25.6 %) | 0.1388 | 91 / 425 | 21.4 % (17.8 %–25.6 %) | 0.1388 |
| `bm25_text` | BM25 keyword search | 57 / 425 | 13.4 % (10.5 %–17.0 %) | 0.0707 | 75 / 425 | 17.6 % (14.3 %–21.6 %) | 0.0876 |
| `dense_e5` | Dense multilingual retrieval (e5) | 131 / 425 | 30.8 % (26.6 %–35.4 %) | 0.1561 | 110 / 425 | 25.9 % (21.9 %–30.2 %) | 0.1330 |
| `bert_encoder` | BERT encoders as recommenders | 94 / 425 | 22.1 % (18.4 %–26.3 %) | 0.1184 | 46 / 425 | 10.8 % (8.2 %–14.1 %) | 0.0485 |
| `hybrid_als_dense` | ALS + dense hybrid | 148 / 425 | 34.8 % (30.4 %–39.5 %) | 0.1931 | 128 / 425 | 30.1 % (25.9 %–34.6 %) | 0.1704 |
| `lightgbm_features` | LightGBM on engineered features | 150 / 425 | 35.3 % (30.9 %–40.0 %) | 0.1681 | 150 / 425 | 35.3 % (30.9 %–40.0 %) | 0.1681 |
| `svm_features` | Linear SVM on engineered features | 65 / 425 | 15.3 % (12.2 %–19.0 %) | 0.0760 | 65 / 425 | 15.3 % (12.2 %–19.0 %) | 0.0760 |
| _guessing_ | random top 10 | — | 9.9 % | — | — | 9.9 % | — |

## Regime `population` · protocol `full`

| arm | what it does | en: hits / n | en: HR@10 (95 % CI) | en: NDCG@10 | cs: hits / n | cs: HR@10 (95 % CI) | cs: NDCG@10 | en: hidden in top 30 / 200 | cs: hidden in top 30 / 200 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `popularity` | Most-bought products | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0024 | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0024 | 2 / 18 | 2 / 18 |
| `als_cf` | ALS collaborative filtering | 3 / 425 | 0.7 % (0.2 %–2.1 %) | 0.0036 | 3 / 425 | 0.7 % (0.2 %–2.1 %) | 0.0036 | 7 / 50 | 7 / 50 |
| `svd_mf` | SVD matrix factorisation | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0008 | 1 / 425 | 0.2 % (0.0 %–1.3 %) | 0.0008 | 5 / 42 | 5 / 42 |
| _guessing_ | random top 10 | — | 0.1 % | — | — | 0.1 % | — | — | — |

## Regime `population` · protocol `sampled`

| arm | what it does | en: hits / n | en: HR@10 (95 % CI) | en: NDCG@10 | cs: hits / n | cs: HR@10 (95 % CI) | cs: NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `popularity` | Most-bought products | 50 / 425 | 11.8 % (9.0 %–15.2 %) | 0.0718 | 50 / 425 | 11.8 % (9.0 %–15.2 %) | 0.0718 |
| `als_cf` | ALS collaborative filtering | 182 / 425 | 42.8 % (38.2 %–47.6 %) | 0.2309 | 182 / 425 | 42.8 % (38.2 %–47.6 %) | 0.2309 |
| `svd_mf` | SVD matrix factorisation | 157 / 425 | 36.9 % (32.5 %–41.6 %) | 0.2083 | 157 / 425 | 36.9 % (32.5 %–41.6 %) | 0.2083 |
| _guessing_ | random top 10 | — | 9.9 % | — | — | 9.9 % | — |

Per-customer ranks and top-10 lists: `scores/<regime>-<arm>-<lang>.json`. Configuration and input identity: `config.json`.
