# UC-04 personality feature — 2026-09-06-personality-feature-2-arms-3-variants-en-cs-425-customers

Ran on: `substrate.db` (sha256 829ee0499dae…), 425 linked customers, 18213 products
When: 2026-09-06, 1 min 21 s
Model calls: none
Variants: none = no personality columns (the recorded arms); inferred = five columns from the model-inferred profile; 425 of 425 customers; sampled = five columns from the generator's sampled profile; 271 of 425 customers, the rest missing
Missing profile: NaN for LightGBM (native handling), the scale midpoint 3.0 for the SVM
Protocols: full, sampled; sampled negatives 100; seed 42

## LightGBM on engineered features

    full, en: none 1, inferred 0, sampled 4                                                                   (hits in the top 10 of 425)
    full, cs: none 1, inferred 0, sampled 4                                                                   (hits in the top 10 of 425)
    sampled, en: none 149, inferred 155, sampled 152                                                          (hits in the top 10 of 425)
    sampled, cs: none 149, inferred 155, sampled 152                                                          (hits in the top 10 of 425)
    inferred vs none, en, full: 0 vs 1 (-1) on 425; only inferred 0, only none 1; sign p 1.0                  (paired on the same customers and candidate lists)
    sampled vs none, en, full: 4 vs 1 (+3) on 271; only sampled 3, only none 0; sign p 0.25                   (paired on the same customers and candidate lists)
    inferred vs sampled, en, full: 0 vs 4 (-4) on 271; only inferred 0, only sampled 4; sign p 0.125          (paired on the same customers and candidate lists)
    inferred vs none, en, sampled: 155 vs 149 (+6) on 425; only inferred 15, only none 9; sign p 0.307        (paired on the same customers and candidate lists)
    sampled vs none, en, sampled: 98 vs 95 (+3) on 271; only sampled 14, only none 11; sign p 0.69            (paired on the same customers and candidate lists)
    inferred vs sampled, en, sampled: 101 vs 98 (+3) on 271; only inferred 17, only sampled 14; sign p 0.72   (paired on the same customers and candidate lists)
    inferred vs none, cs, full: 0 vs 1 (-1) on 425; only inferred 0, only none 1; sign p 1.0                  (paired on the same customers and candidate lists)
    sampled vs none, cs, full: 4 vs 1 (+3) on 271; only sampled 3, only none 0; sign p 0.25                   (paired on the same customers and candidate lists)
    inferred vs sampled, cs, full: 0 vs 4 (-4) on 271; only inferred 0, only sampled 4; sign p 0.125          (paired on the same customers and candidate lists)
    inferred vs none, cs, sampled: 155 vs 149 (+6) on 425; only inferred 15, only none 9; sign p 0.307        (paired on the same customers and candidate lists)
    sampled vs none, cs, sampled: 98 vs 95 (+3) on 271; only sampled 14, only none 11; sign p 0.69            (paired on the same customers and candidate lists)
    inferred vs sampled, cs, sampled: 101 vs 98 (+3) on 271; only inferred 17, only sampled 14; sign p 0.72   (paired on the same customers and candidate lists)

## Linear SVM on engineered features

    full, en: none 1, inferred 1, sampled 1                                                                   (hits in the top 10 of 425)
    full, cs: none 1, inferred 1, sampled 1                                                                   (hits in the top 10 of 425)
    sampled, en: none 65, inferred 65, sampled 65                                                             (hits in the top 10 of 425)
    sampled, cs: none 65, inferred 65, sampled 65                                                             (hits in the top 10 of 425)
    inferred vs none, en, full: 1 vs 1 (+0) on 425; only inferred 0, only none 0; sign p 1.0                  (paired on the same customers and candidate lists)
    sampled vs none, en, full: 1 vs 1 (+0) on 271; only sampled 0, only none 0; sign p 1.0                    (paired on the same customers and candidate lists)
    inferred vs sampled, en, full: 1 vs 1 (+0) on 271; only inferred 0, only sampled 0; sign p 1.0            (paired on the same customers and candidate lists)
    inferred vs none, en, sampled: 65 vs 65 (+0) on 425; only inferred 0, only none 0; sign p 1.0             (paired on the same customers and candidate lists)
    sampled vs none, en, sampled: 44 vs 44 (+0) on 271; only sampled 0, only none 0; sign p 1.0               (paired on the same customers and candidate lists)
    inferred vs sampled, en, sampled: 44 vs 44 (+0) on 271; only inferred 0, only sampled 0; sign p 1.0       (paired on the same customers and candidate lists)
    inferred vs none, cs, full: 1 vs 1 (+0) on 425; only inferred 0, only none 0; sign p 1.0                  (paired on the same customers and candidate lists)
    sampled vs none, cs, full: 1 vs 1 (+0) on 271; only sampled 0, only none 0; sign p 1.0                    (paired on the same customers and candidate lists)
    inferred vs sampled, cs, full: 1 vs 1 (+0) on 271; only inferred 0, only sampled 0; sign p 1.0            (paired on the same customers and candidate lists)
    inferred vs none, cs, sampled: 65 vs 65 (+0) on 425; only inferred 0, only none 0; sign p 1.0             (paired on the same customers and candidate lists)
    sampled vs none, cs, sampled: 44 vs 44 (+0) on 271; only sampled 0, only none 0; sign p 1.0               (paired on the same customers and candidate lists)
    inferred vs sampled, cs, sampled: 44 vs 44 (+0) on 271; only inferred 0, only sampled 0; sign p 1.0       (paired on the same customers and candidate lists)
    identical rankings by construction                                                                        (a linear model adds the same term to every product of a customer for a customer-level column, so the order inside a customer cannot change; zero discordant pairs is the expected outcome and the check that the pairing works)

The largest paired difference is +6 hits of 425 (lightgbm_features, inferred vs none, en, sampled); no pair passes the sign test at 5 %, so on this data a Big Five profile, inferred or sampled, adds nothing measurable to a classical recommender. LightGBM moves by a few hits between runs even with pinned threads, so differences of that size are noise; the linear SVM cannot react to a customer-level column at all (identical rankings by construction).
