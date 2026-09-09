# Výsledky arény UC-04 (příloha, generováno)

Vygenerováno ze složky běhu `ucs/uc04_matchmaker/eval/runs/2026-09-07-arena-crm-population-12-arms-en-cs-425-customers/` (běh ze dne 2026-09-07, 351 s). Databáze `substrate.db` (sha256 aba47a161d87…), 425 zákazníků, 18213 produktů, seed 42. Bez volání jazykového modelu. Všechna ramena jsou nasazená se semínkem a opakovaný běh nad touž databází dává tatáž čísla; jedinou výjimkou je LightGBM, které se mezi běhy liší o jednotky zásahů uvnitř svého intervalu spolehlivosti. Tabulky jsou široké; stránka přílohy se sází na šířku.

Skrytou položkou je chronologicky poslední nákup zákazníka. Úplný katalog: skrytá položka se řadí proti všem 18213 produktům, náhodný tip dává v top 10 0,1 %. Vzorkovaný protokol: skrytá položka se řadí proti 100 náhodným nekoupeným produktům, stejným pro všechna ramena, náhodný tip dává 9,9 %. Vzorkovaný protokol je snazší úloha a jeho čísla nejsou srovnatelná s úplným katalogem; slouží ke srovnání metod mezi sebou, ne k odhadu, co by viděl obchod. Česká větev: same customers, histories and hidden items; review text, headline and product title in Czech (title for 16 067 of 18 213 products, empty text for 3 207 untranslated reviews); descriptions stay English (D-UC04-D).

Tabulka 1 – Zásahy v top 10 z 425 zákazníků, úplný katalog, režim CRM (učení jen ze zákazníků obchodu)

| rameno | metoda | anglická větev: zásahy | anglická větev: HR@10 (95% IS) | česká větev: zásahy | česká větev: HR@10 (95% IS) | anglická větev: skrytá v top 30 / 200 | česká větev: skrytá v top 30 / 200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `adamic_adar` | Adamic-Adar link prediction | 3 / 425 | 0,7 % (0,2 %–2,1 %) | 3 / 425 | 0,7 % (0,2 %–2,1 %) | 10 / 53 | 10 / 53 |
| `als_cf` | ALS collaborative filtering | 6 / 425 | 1,4 % (0,7 %–3,0 %) | 6 / 425 | 1,4 % (0,7 %–3,0 %) | 12 / 45 | 12 / 45 |
| `apriori_rules` | Apriori association rules | 5 / 425 | 1,2 % (0,5 %–2,7 %) | 5 / 425 | 1,2 % (0,5 %–2,7 %) | 14 / 48 | 14 / 48 |
| `bert_encoder` | BERT encoders as recommenders | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 2 / 19 | 1 / 4 |
| `bm25_text` | BM25 keyword search | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 2 / 425 | 0,5 % (0,1 %–1,7 %) | 2 / 13 | 4 / 14 |
| `dense_e5` | Dense multilingual retrieval (e5) | 4 / 425 | 0,9 % (0,4 %–2,4 %) | 2 / 425 | 0,5 % (0,1 %–1,7 %) | 7 / 26 | 4 / 20 |
| `hybrid_als_dense` | ALS + dense hybrid | 8 / 425 | 1,9 % (1,0 %–3,7 %) | 7 / 425 | 1,7 % (0,8 %–3,4 %) | 19 / 36 | 13 / 35 |
| `lightgbm_features` | LightGBM on engineered features | 3 / 425 | 0,7 % (0,2 %–2,1 %) | 3 / 425 | 0,7 % (0,2 %–2,1 %) | 5 / 21 | 5 / 21 |
| `naive_bayes` | Naive Bayes over the purchase history | 4 / 425 | 0,9 % (0,4 %–2,4 %) | 4 / 425 | 0,9 % (0,4 %–2,4 %) | 10 / 40 | 10 / 40 |
| `popularity` | Most-bought products | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 5 / 33 | 5 / 33 |
| `svd_mf` | SVD matrix factorisation | 6 / 425 | 1,4 % (0,7 %–3,0 %) | 6 / 425 | 1,4 % (0,7 %–3,0 %) | 16 / 48 | 16 / 48 |
| `svm_features` | Linear SVM on engineered features | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 3 / 12 | 3 / 12 |
| _náhodný tip_ | top 10 náhodně | — | 0,1 % | — | 0,1 % | — | — |

Tabulka 2 – Zásahy v top 10 z 425 zákazníků, vzorkovaný (1 skrytý + 100 náhodných nekoupených), režim CRM (učení jen ze zákazníků obchodu)

| rameno | metoda | anglická větev: zásahy | anglická větev: HR@10 (95% IS) | česká větev: zásahy | česká větev: HR@10 (95% IS) |
| --- | --- | --- | --- | --- | --- |
| `adamic_adar` | Adamic-Adar link prediction | 154 / 425 | 36,2 % (31,8 %–40,9 %) | 154 / 425 | 36,2 % (31,8 %–40,9 %) |
| `als_cf` | ALS collaborative filtering | 119 / 425 | 28,0 % (23,9 %–32,5 %) | 119 / 425 | 28,0 % (23,9 %–32,5 %) |
| `apriori_rules` | Apriori association rules | 110 / 425 | 25,9 % (21,9 %–30,2 %) | 110 / 425 | 25,9 % (21,9 %–30,2 %) |
| `bert_encoder` | BERT encoders as recommenders | 94 / 425 | 22,1 % (18,4 %–26,3 %) | 46 / 425 | 10,8 % (8,2 %–14,1 %) |
| `bm25_text` | BM25 keyword search | 57 / 425 | 13,4 % (10,5 %–17,0 %) | 75 / 425 | 17,6 % (14,3 %–21,6 %) |
| `dense_e5` | Dense multilingual retrieval (e5) | 131 / 425 | 30,8 % (26,6 %–35,4 %) | 110 / 425 | 25,9 % (21,9 %–30,2 %) |
| `hybrid_als_dense` | ALS + dense hybrid | 148 / 425 | 34,8 % (30,4 %–39,5 %) | 128 / 425 | 30,1 % (25,9 %–34,6 %) |
| `lightgbm_features` | LightGBM on engineered features | 145 / 425 | 34,1 % (29,8 %–38,8 %) | 145 / 425 | 34,1 % (29,8 %–38,8 %) |
| `naive_bayes` | Naive Bayes over the purchase history | 91 / 425 | 21,4 % (17,8 %–25,6 %) | 91 / 425 | 21,4 % (17,8 %–25,6 %) |
| `popularity` | Most-bought products | 125 / 425 | 29,4 % (25,3 %–33,9 %) | 125 / 425 | 29,4 % (25,3 %–33,9 %) |
| `svd_mf` | SVD matrix factorisation | 125 / 425 | 29,4 % (25,3 %–33,9 %) | 125 / 425 | 29,4 % (25,3 %–33,9 %) |
| `svm_features` | Linear SVM on engineered features | 65 / 425 | 15,3 % (12,2 %–19,0 %) | 65 / 425 | 15,3 % (12,2 %–19,0 %) |
| _náhodný tip_ | top 10 náhodně | — | 9,9 % | — | 9,9 % |

Tabulka 3 – Zásahy v top 10 z 425 zákazníků, úplný katalog, režim populace (učení z celého veřejného datasetu)

| rameno | metoda | anglická větev: zásahy | anglická větev: HR@10 (95% IS) | česká větev: zásahy | česká větev: HR@10 (95% IS) | anglická větev: skrytá v top 30 / 200 | česká větev: skrytá v top 30 / 200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `als_cf` | ALS collaborative filtering | 3 / 425 | 0,7 % (0,2 %–2,1 %) | 3 / 425 | 0,7 % (0,2 %–2,1 %) | 7 / 50 | 7 / 50 |
| `popularity` | Most-bought products | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 2 / 18 | 2 / 18 |
| `svd_mf` | SVD matrix factorisation | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 1 / 425 | 0,2 % (0,0 %–1,3 %) | 5 / 42 | 5 / 42 |
| _náhodný tip_ | top 10 náhodně | — | 0,1 % | — | 0,1 % | — | — |

Tabulka 4 – Zásahy v top 10 z 425 zákazníků, vzorkovaný (1 skrytý + 100 náhodných nekoupených), režim populace (učení z celého veřejného datasetu)

| rameno | metoda | anglická větev: zásahy | anglická větev: HR@10 (95% IS) | česká větev: zásahy | česká větev: HR@10 (95% IS) |
| --- | --- | --- | --- | --- | --- |
| `als_cf` | ALS collaborative filtering | 182 / 425 | 42,8 % (38,2 %–47,6 %) | 182 / 425 | 42,8 % (38,2 %–47,6 %) |
| `popularity` | Most-bought products | 50 / 425 | 11,8 % (9,0 %–15,2 %) | 50 / 425 | 11,8 % (9,0 %–15,2 %) |
| `svd_mf` | SVD matrix factorisation | 157 / 425 | 36,9 % (32,5 %–41,6 %) | 157 / 425 | 36,9 % (32,5 %–41,6 %) |
| _náhodný tip_ | top 10 náhodně | — | 9,9 % | — | 9,9 % |

Zdrojová data po řádcích: `attachments/uc04-arena-results.csv`; pořadí a top 10 každého zákazníka: `scores/` ve složce běhu.
