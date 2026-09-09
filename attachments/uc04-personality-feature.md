# Sloupec osobnosti v klasickém rameni UC-04 (příloha, generováno)

Vygenerováno ze složky běhu `ucs/uc04_matchmaker/eval/runs/2026-09-07-personality-feature-2-arms-3-variants-en-cs-425-customers/` (běh ze dne 2026-09-07, databáze `substrate.db`, sha256 aba47a161d87…). Bez volání jazykového modelu. Tři varianty téhož ramene na týchž zákaznících, kandidátních listinách a seedech: bez profilu, s odvozeným profilem (425 of 425 customers), se vzorkovaným profilem (271 of 425 customers, the rest missing). Chybějící profil: NaN for LightGBM (native handling), the scale midpoint 3.0 for the SVM. U lineárního SVM se pořadí uvnitř zákazníka změnit nemůže: sloupec na úrovni zákazníka přičte každému jeho produktu tentýž člen, takže nula diskordantních párů je očekávaný výsledek a zároveň kontrola párování; sloupec osobnosti může využít jen model s interakcemi (stromy).

Tabulka 1 – LightGBM on engineered features, úplný katalog: zásahy v top 10 z 425 zákazníků podle varianty

| varianta | anglická větev | česká větev |
| --- | --- | --- |
| bez profilu | 2 (0.1 až 1.7 %) | 2 (0.1 až 1.7 %) |
| odvozený profil | 1 (0.0 až 1.3 %) | 1 (0.0 až 1.3 %) |
| vzorkovaný profil | 2 (0.1 až 1.7 %) | 2 (0.1 až 1.7 %) |

Tabulka 2 – LightGBM on engineered features, vzorkovaný (1 + 100): zásahy v top 10 z 425 zákazníků podle varianty

| varianta | anglická větev | česká větev |
| --- | --- | --- |
| bez profilu | 151 (31.1 až 40.2 %) | 151 (31.1 až 40.2 %) |
| odvozený profil | 152 (31.4 až 40.4 %) | 152 (31.4 až 40.4 %) |
| vzorkovaný profil | 151 (31.1 až 40.2 %) | 151 (31.1 až 40.2 %) |

Tabulka 3 – Linear SVM on engineered features, úplný katalog: zásahy v top 10 z 425 zákazníků podle varianty

| varianta | anglická větev | česká větev |
| --- | --- | --- |
| bez profilu | 1 (0.0 až 1.3 %) | 1 (0.0 až 1.3 %) |
| odvozený profil | 1 (0.0 až 1.3 %) | 1 (0.0 až 1.3 %) |
| vzorkovaný profil | 1 (0.0 až 1.3 %) | 1 (0.0 až 1.3 %) |

Tabulka 4 – Linear SVM on engineered features, vzorkovaný (1 + 100): zásahy v top 10 z 425 zákazníků podle varianty

| varianta | anglická větev | česká větev |
| --- | --- | --- |
| bez profilu | 65 (12.2 až 19.0 %) | 65 (12.2 až 19.0 %) |
| odvozený profil | 65 (12.2 až 19.0 %) | 65 (12.2 až 19.0 %) |
| vzorkovaný profil | 65 (12.2 až 19.0 %) | 65 (12.2 až 19.0 %) |

Tabulka 5 – Párové rozdíly (zásah = skrytý produkt v top 10; diskordantní páry a znaménkový test)

| rameno | větev | protokol | dvojice | n | zásahy | rozdíl | jen první / jen druhá | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lightgbm_features` | anglická větev | úplný katalog | odvozený profil vs bez profilu | 425 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| `lightgbm_features` | anglická větev | úplný katalog | vzorkovaný profil vs bez profilu | 271 | 2 vs 2 | +0 | 1 / 1 | 1.0 |
| `lightgbm_features` | anglická větev | úplný katalog | odvozený profil vs vzorkovaný profil | 271 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| `lightgbm_features` | anglická větev | vzorkovaný (1 + 100) | odvozený profil vs bez profilu | 425 | 152 vs 151 | +1 | 23 / 22 | 1.0 |
| `lightgbm_features` | anglická větev | vzorkovaný (1 + 100) | vzorkovaný profil vs bez profilu | 271 | 96 vs 99 | -3 | 13 / 16 | 0.711 |
| `lightgbm_features` | anglická větev | vzorkovaný (1 + 100) | odvozený profil vs vzorkovaný profil | 271 | 100 vs 96 | +4 | 15 / 11 | 0.557 |
| `lightgbm_features` | česká větev | úplný katalog | odvozený profil vs bez profilu | 425 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| `lightgbm_features` | česká větev | úplný katalog | vzorkovaný profil vs bez profilu | 271 | 2 vs 2 | +0 | 1 / 1 | 1.0 |
| `lightgbm_features` | česká větev | úplný katalog | odvozený profil vs vzorkovaný profil | 271 | 1 vs 2 | -1 | 1 / 2 | 1.0 |
| `lightgbm_features` | česká větev | vzorkovaný (1 + 100) | odvozený profil vs bez profilu | 425 | 152 vs 151 | +1 | 23 / 22 | 1.0 |
| `lightgbm_features` | česká větev | vzorkovaný (1 + 100) | vzorkovaný profil vs bez profilu | 271 | 96 vs 99 | -3 | 13 / 16 | 0.711 |
| `lightgbm_features` | česká větev | vzorkovaný (1 + 100) | odvozený profil vs vzorkovaný profil | 271 | 100 vs 96 | +4 | 15 / 11 | 0.557 |
| `svm_features` | anglická větev | úplný katalog | odvozený profil vs bez profilu | 425 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| `svm_features` | anglická větev | úplný katalog | vzorkovaný profil vs bez profilu | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| `svm_features` | anglická větev | úplný katalog | odvozený profil vs vzorkovaný profil | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| `svm_features` | anglická větev | vzorkovaný (1 + 100) | odvozený profil vs bez profilu | 425 | 65 vs 65 | +0 | 0 / 0 | 1.0 |
| `svm_features` | anglická větev | vzorkovaný (1 + 100) | vzorkovaný profil vs bez profilu | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
| `svm_features` | anglická větev | vzorkovaný (1 + 100) | odvozený profil vs vzorkovaný profil | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
| `svm_features` | česká větev | úplný katalog | odvozený profil vs bez profilu | 425 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| `svm_features` | česká větev | úplný katalog | vzorkovaný profil vs bez profilu | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| `svm_features` | česká větev | úplný katalog | odvozený profil vs vzorkovaný profil | 271 | 1 vs 1 | +0 | 0 / 0 | 1.0 |
| `svm_features` | česká větev | vzorkovaný (1 + 100) | odvozený profil vs bez profilu | 425 | 65 vs 65 | +0 | 0 / 0 | 1.0 |
| `svm_features` | česká větev | vzorkovaný (1 + 100) | vzorkovaný profil vs bez profilu | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
| `svm_features` | česká větev | vzorkovaný (1 + 100) | odvozený profil vs vzorkovaný profil | 271 | 44 vs 44 | +0 | 0 / 0 | 1.0 |
