# UC-04 arena results — 2026-09-07-arena-crm-population-12-arms-en-cs-425-customers

Ran on: `substrate.db` (sha256 aba47a161d87…), 425 linked customers, 18213 products
Regimes: crm, population; population = 192403 users / 1689188 reviews from `reviews_Electronics_5.json.gz`
Protocols: full, sampled; sampled negatives 100; seed 42
When: 2026-09-07, 5 min 51 s in total
Czech branch: same customers, histories and hidden items; review text, headline and product title in Czech (title for 16 067 of 18 213 products, empty text for 3 207 untranslated reviews); descriptions stay English (D-UC04-D)
Model calls: none (classical arms only)

## regime crm, protocol full (guessing 0.1 %)

    popularity en: 1/425 hits@10, HR 0.2 %             (Most-bought products; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 0.0 s)
    popularity cs: 1/425 hits@10, HR 0.2 %             (Most-bought products; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 0.0 s)
    als_cf en: 6/425 hits@10, HR 1.4 %                 (ALS collaborative filtering; 95 % CI 0.6 %–3.0 %; NDCG@10 0.006; 0.5 s)
    als_cf cs: 6/425 hits@10, HR 1.4 %                 (ALS collaborative filtering; 95 % CI 0.6 %–3.0 %; NDCG@10 0.006; 0.6 s)
    svd_mf en: 6/425 hits@10, HR 1.4 %                 (SVD matrix factorisation; 95 % CI 0.6 %–3.0 %; NDCG@10 0.008; 0.0 s)
    svd_mf cs: 6/425 hits@10, HR 1.4 %                 (SVD matrix factorisation; 95 % CI 0.6 %–3.0 %; NDCG@10 0.008; 0.0 s)
    apriori_rules en: 5/425 hits@10, HR 1.2 %          (Apriori association rules; 95 % CI 0.5 %–2.7 %; NDCG@10 0.005; 3.0 s)
    apriori_rules cs: 5/425 hits@10, HR 1.2 %          (Apriori association rules; 95 % CI 0.5 %–2.7 %; NDCG@10 0.005; 2.6 s)
    adamic_adar en: 3/425 hits@10, HR 0.7 %            (Adamic-Adar link prediction; 95 % CI 0.2 %–2.1 %; NDCG@10 0.003; 4.4 s)
    adamic_adar cs: 3/425 hits@10, HR 0.7 %            (Adamic-Adar link prediction; 95 % CI 0.2 %–2.1 %; NDCG@10 0.003; 4.6 s)
    naive_bayes en: 4/425 hits@10, HR 0.9 %            (Naive Bayes over the purchase history; 95 % CI 0.4 %–2.4 %; NDCG@10 0.004; 5.7 s)
    naive_bayes cs: 4/425 hits@10, HR 0.9 %            (Naive Bayes over the purchase history; 95 % CI 0.4 %–2.4 %; NDCG@10 0.004; 5.7 s)
    bm25_text en: 1/425 hits@10, HR 0.2 %              (BM25 keyword search; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 160.5 s)
    bm25_text cs: 2/425 hits@10, HR 0.5 %              (BM25 keyword search; 95 % CI 0.1 %–1.7 %; NDCG@10 0.002; 90.7 s)
    dense_e5 en: 4/425 hits@10, HR 0.9 %               (Dense multilingual retrieval (e5); 95 % CI 0.4 %–2.4 %; NDCG@10 0.004; 0.1 s)
    dense_e5 cs: 2/425 hits@10, HR 0.5 %               (Dense multilingual retrieval (e5); 95 % CI 0.1 %–1.7 %; NDCG@10 0.002; 0.1 s)
    bert_encoder en: 1/425 hits@10, HR 0.2 %           (BERT encoders as recommenders; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 0.1 s)
    bert_encoder cs: 1/425 hits@10, HR 0.2 %           (BERT encoders as recommenders; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 0.1 s)
    hybrid_als_dense en: 8/425 hits@10, HR 1.9 %       (ALS + dense hybrid; 95 % CI 1.0 %–3.7 %; NDCG@10 0.008; 0.5 s)
    hybrid_als_dense cs: 7/425 hits@10, HR 1.6 %       (ALS + dense hybrid; 95 % CI 0.8 %–3.4 %; NDCG@10 0.008; 0.5 s)
    lightgbm_features en: 3/425 hits@10, HR 0.7 %      (LightGBM on engineered features; 95 % CI 0.2 %–2.1 %; NDCG@10 0.002; 8.5 s)
    lightgbm_features cs: 3/425 hits@10, HR 0.7 %      (LightGBM on engineered features; 95 % CI 0.2 %–2.1 %; NDCG@10 0.002; 8.5 s)
    svm_features en: 1/425 hits@10, HR 0.2 %           (Linear SVM on engineered features; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 3.3 s)
    svm_features cs: 1/425 hits@10, HR 0.2 %           (Linear SVM on engineered features; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 3.4 s)

## regime crm, protocol sampled (guessing 9.9 %)

    popularity en: 125/425 hits@10, HR 29.4 %          (Most-bought products; 95 % CI 25.3 %–33.9 %; NDCG@10 0.165; 0.0 s)
    popularity cs: 125/425 hits@10, HR 29.4 %          (Most-bought products; 95 % CI 25.3 %–33.9 %; NDCG@10 0.165; 0.0 s)
    als_cf en: 119/425 hits@10, HR 28.0 %              (ALS collaborative filtering; 95 % CI 23.9 %–32.5 %; NDCG@10 0.167; 0.5 s)
    als_cf cs: 119/425 hits@10, HR 28.0 %              (ALS collaborative filtering; 95 % CI 23.9 %–32.5 %; NDCG@10 0.167; 0.6 s)
    svd_mf en: 125/425 hits@10, HR 29.4 %              (SVD matrix factorisation; 95 % CI 25.3 %–33.9 %; NDCG@10 0.184; 0.0 s)
    svd_mf cs: 125/425 hits@10, HR 29.4 %              (SVD matrix factorisation; 95 % CI 25.3 %–33.9 %; NDCG@10 0.184; 0.0 s)
    apriori_rules en: 110/425 hits@10, HR 25.9 %       (Apriori association rules; 95 % CI 21.9 %–30.2 %; NDCG@10 0.171; 3.0 s)
    apriori_rules cs: 110/425 hits@10, HR 25.9 %       (Apriori association rules; 95 % CI 21.9 %–30.2 %; NDCG@10 0.171; 2.6 s)
    adamic_adar en: 154/425 hits@10, HR 36.2 %         (Adamic-Adar link prediction; 95 % CI 31.8 %–40.9 %; NDCG@10 0.219; 4.4 s)
    adamic_adar cs: 154/425 hits@10, HR 36.2 %         (Adamic-Adar link prediction; 95 % CI 31.8 %–40.9 %; NDCG@10 0.219; 4.6 s)
    naive_bayes en: 91/425 hits@10, HR 21.4 %          (Naive Bayes over the purchase history; 95 % CI 17.8 %–25.6 %; NDCG@10 0.139; 5.7 s)
    naive_bayes cs: 91/425 hits@10, HR 21.4 %          (Naive Bayes over the purchase history; 95 % CI 17.8 %–25.6 %; NDCG@10 0.139; 5.7 s)
    bm25_text en: 57/425 hits@10, HR 13.4 %            (BM25 keyword search; 95 % CI 10.5 %–17.0 %; NDCG@10 0.071; 160.5 s)
    bm25_text cs: 75/425 hits@10, HR 17.6 %            (BM25 keyword search; 95 % CI 14.3 %–21.6 %; NDCG@10 0.088; 90.7 s)
    dense_e5 en: 131/425 hits@10, HR 30.8 %            (Dense multilingual retrieval (e5); 95 % CI 26.6 %–35.4 %; NDCG@10 0.156; 0.1 s)
    dense_e5 cs: 110/425 hits@10, HR 25.9 %            (Dense multilingual retrieval (e5); 95 % CI 21.9 %–30.2 %; NDCG@10 0.133; 0.1 s)
    bert_encoder en: 94/425 hits@10, HR 22.1 %         (BERT encoders as recommenders; 95 % CI 18.4 %–26.3 %; NDCG@10 0.118; 0.1 s)
    bert_encoder cs: 46/425 hits@10, HR 10.8 %         (BERT encoders as recommenders; 95 % CI 8.2 %–14.1 %; NDCG@10 0.048; 0.1 s)
    hybrid_als_dense en: 148/425 hits@10, HR 34.8 %    (ALS + dense hybrid; 95 % CI 30.4 %–39.5 %; NDCG@10 0.193; 0.5 s)
    hybrid_als_dense cs: 128/425 hits@10, HR 30.1 %    (ALS + dense hybrid; 95 % CI 25.9 %–34.6 %; NDCG@10 0.170; 0.5 s)
    lightgbm_features en: 145/425 hits@10, HR 34.1 %   (LightGBM on engineered features; 95 % CI 29.8 %–38.7 %; NDCG@10 0.166; 8.5 s)
    lightgbm_features cs: 145/425 hits@10, HR 34.1 %   (LightGBM on engineered features; 95 % CI 29.8 %–38.7 %; NDCG@10 0.166; 8.5 s)
    svm_features en: 65/425 hits@10, HR 15.3 %         (Linear SVM on engineered features; 95 % CI 12.2 %–19.0 %; NDCG@10 0.076; 3.3 s)
    svm_features cs: 65/425 hits@10, HR 15.3 %         (Linear SVM on engineered features; 95 % CI 12.2 %–19.0 %; NDCG@10 0.076; 3.4 s)

## regime population, protocol full (guessing 0.1 %)

    popularity en: 1/425 hits@10, HR 0.2 %             (Most-bought products; 95 % CI 0.0 %–1.3 %; NDCG@10 0.002; 0.0 s)
    popularity cs: 1/425 hits@10, HR 0.2 %             (Most-bought products; 95 % CI 0.0 %–1.3 %; NDCG@10 0.002; 0.0 s)
    als_cf en: 3/425 hits@10, HR 0.7 %                 (ALS collaborative filtering; 95 % CI 0.2 %–2.1 %; NDCG@10 0.004; 5.6 s)
    als_cf cs: 3/425 hits@10, HR 0.7 %                 (ALS collaborative filtering; 95 % CI 0.2 %–2.1 %; NDCG@10 0.004; 5.6 s)
    svd_mf en: 1/425 hits@10, HR 0.2 %                 (SVD matrix factorisation; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 1.1 s)
    svd_mf cs: 1/425 hits@10, HR 0.2 %                 (SVD matrix factorisation; 95 % CI 0.0 %–1.3 %; NDCG@10 0.001; 1.1 s)

## regime population, protocol sampled (guessing 9.9 %)

    popularity en: 50/425 hits@10, HR 11.8 %           (Most-bought products; 95 % CI 9.0 %–15.2 %; NDCG@10 0.072; 0.0 s)
    popularity cs: 50/425 hits@10, HR 11.8 %           (Most-bought products; 95 % CI 9.0 %–15.2 %; NDCG@10 0.072; 0.0 s)
    als_cf en: 182/425 hits@10, HR 42.8 %              (ALS collaborative filtering; 95 % CI 38.2 %–47.6 %; NDCG@10 0.231; 5.6 s)
    als_cf cs: 182/425 hits@10, HR 42.8 %              (ALS collaborative filtering; 95 % CI 38.2 %–47.6 %; NDCG@10 0.231; 5.6 s)
    svd_mf en: 157/425 hits@10, HR 36.9 %              (SVD matrix factorisation; 95 % CI 32.5 %–41.6 %; NDCG@10 0.208; 1.1 s)
    svd_mf cs: 157/425 hits@10, HR 36.9 %              (SVD matrix factorisation; 95 % CI 32.5 %–41.6 %; NDCG@10 0.208; 1.1 s)

Read the two protocols apart: under `full` in regime `crm` the best arm was `hybrid_als_dense` with 8 of 425 hits at top 10 against 0.2 expected by guessing; under `sampled` in regime `crm` the best arm was `adamic_adar` with 154 of 425 hits at top 10 against 42.1 expected by guessing; under `full` in regime `population` the best arm was `als_cf` with 3 of 425 hits at top 10 against 0.2 expected by guessing; under `sampled` in regime `population` the best arm was `als_cf` with 182 of 425 hits at top 10 against 42.1 expected by guessing.
