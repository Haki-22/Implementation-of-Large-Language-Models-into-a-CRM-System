# Metody arény UC-04 (příloha, generováno z registrů)

Vygenerováno dne 2026-09-07 z `arms/__init__.py` (12 klasických metod) a `arms/model/__init__.py` (5 metod s jazykovým modelem). Toto je jediný popis metod v práci; text kapitoly na tuto tabulku odkazuje a metody znovu nepopisuje. Klasické metody se hodnotí pod oběma protokoly na všech 425 zákaznících; metody s modelem pod protokolem, který je u nich uveden, na pevném vzorku 100 zákazníků (metoda nad ALS top 200 na zákaznících, jimž ALS dostalo skrytý nákup do prvních dvou set).

Tabulka – Metody arény: jméno v kódu, co metoda dělá, rodina, vstup z klasického modelu, protokol

| metoda | co to je | rodina | vstup z ML | protokol |
| --- | --- | --- | --- | --- |
| `popularity` | Most-bought products: ranks every product by how many customers bought it; no personalisation | classical / baseline | — | úplný katalog i vzorkovaný |
| `als_cf` | ALS collaborative filtering: latent factors from who bought what; a purchase weighs 1 + rating; 64 factors, 20 iterations | classical / collaborative filtering | — | úplný katalog i vzorkovaný |
| `svd_mf` | SVD matrix factorisation: truncated SVD of the explicit rating matrix, 50 factors | classical / collaborative filtering | — | úplný katalog i vzorkovaný |
| `apriori_rules` | Apriori association rules: frequent product pairs (support 0.006, top-2 000 products) as rules scored by lift x confidence | classical / association rules | — | úplný katalog i vzorkovaný |
| `adamic_adar` | Adamic-Adar link prediction: co-buyer paths through the customer-product graph, weighted 1 / log(degree) | classical / graph | — | úplný katalog i vzorkovaný |
| `naive_bayes` | Naive Bayes over the purchase history: multinomial naive Bayes, bought products as features, the 500 most-bought products as classes | classical / probabilistic | — | úplný katalog i vzorkovaný |
| `bm25_text` | BM25 keyword search: the customer's 200 most frequent review words (lemmatised in Czech) against product title, category and description | classical / lexical retrieval | — | úplný katalog i vzorkovaný |
| `dense_e5` | Dense multilingual retrieval (e5): multilingual-e5-base vectors of product texts; a customer is the mean of the products bought; cosine similarity | trained encoder / dense retrieval | — | úplný katalog i vzorkovaný |
| `bert_encoder` | BERT encoders as recommenders: [CLS] vectors of product texts from DistilBERT (en) or Czert-B (cs), no fine-tuning; cosine to the customer's mean vector | trained encoder / no task training | — | úplný katalog i vzorkovaný |
| `hybrid_als_dense` | ALS + dense hybrid: equal-weight sum of per-customer min-max scaled ALS and dense-retrieval scores | classical / hybrid | — | úplný katalog i vzorkovaný |
| `lightgbm_features` | LightGBM on engineered features: boosted trees, bought-or-not, over category, price, length and history-overlap features | classical / gradient boosting | — | úplný katalog i vzorkovaný |
| `svm_features` | Linear SVM on engineered features: linear SVM, bought-or-not, over the same features as the LightGBM arm | classical / linear | — | úplný katalog i vzorkovaný |
| `rank_candidates` | Model ranks the candidates alone: whole history + the 101 sampled candidates in a seeded random order; the model returns the full permutation; no classical input | language model / zero-shot ranking | none | vzorkovaný (1 skrytý + 100 náhodných nekoupených) |
| `describe_and_retrieve` | Model describes the next purchase, the catalogue index retrieves it: whole history -> three listing lines for the next purchase -> multilingual-e5 query vectors against the cached catalogue vectors; score = best cosine over the three lines | language model / description + dense retrieval | the dense e5 index of the catalogue (the dense_e5 arm's cached vectors) | úplný katalog, vzorkovaný (1 skrytý + 100 náhodných nekoupených) |
| `rerank_als` | Model re-ranks the ALS order: whole history + the 101 sampled candidates in ALS order with their scores; the model may move a candidate only where the history supports it | language model / re-ranking over collaborative filtering | ALS order and scores of the 101 sampled candidates | vzorkovaný (1 skrytý + 100 náhodných nekoupených) |
| `rerank_als_with_profile` | Model re-ranks the ALS order with the customer profile: method 3 plus the profile from the CRM: Big Five estimate, lifecycle stage, interest topics, persona and aspects where present; the profile breaks ties only | language model / re-ranking over collaborative filtering + profile | ALS order and scores of the 101 sampled candidates; the profile from the database | vzorkovaný (1 skrytý + 100 náhodných nekoupených) |
| `rerank_als_top200` | Model re-ranks the ALS top 200 (full catalogue): for the customers whose hidden item ALS placed within its top 200: those 200 in ALS order with scores, the model re-orders them; the honest test against the whole catalogue | language model / re-ranking over collaborative filtering | ALS top 200 of the whole catalogue, with scores | úplný katalog |

