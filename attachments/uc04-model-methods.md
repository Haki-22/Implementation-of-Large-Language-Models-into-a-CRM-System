# Metody s jazykovým modelem v aréně UC-04 (příloha, generováno)

Vygenerováno ze složek běhů pod `ucs/uc04_matchmaker/eval/runs/`, jedna složka na metodu: `2026-09-07-model-methods-1-methods-agy-gemini-3.8-flash-medium-en-cs-100-customers-2` (rank_candidates: agy / gemini-3.8-flash / medium, CLI 1.1.27, prompt 1.0.2, běh ze dne 2026-09-07, 37 s); `2026-09-07-model-methods-2-methods-codex-gpt-5.5-low-en-cs-100-customers-3` (rerank_als, rerank_als_with_profile: codex / gpt-5.5 / low, CLI codex-cli 0.153.4, prompt 1.0.2, běh ze dne 2026-09-07, 11 s); `2026-09-07-model-methods-describe-and-retrieve-agy-gemini-3.8-flash-medium-en-cs-100-customers` (describe_and_retrieve: agy / gemini-3.8-flash / medium, CLI 1.1.27, prompt 1.0.2, běh ze dne 2026-09-07, 37 s); `2026-09-07-model-methods-rerank-als-top200-codex-gpt-5.5-low-en-cs-100-customers` (rerank_als_top200: codex / gpt-5.5 / low, CLI codex-cli 0.153.4, prompt 1.0.2, běh ze dne 2026-09-07, 38 s). Databáze `substrate.db` (sha256 aba47a161d87…); vzorek `model-arms-100` (100 zákazníků, pravidlo ve složce běhu), metoda nad ALS top 200 na zákaznících, jimž ALS dostalo skrytý nákup do prvních dvou set. Metody běžely po poskytovatelích (rozhodnutí 2026-09-07); dvojice metoda 3 × metoda 4 je uvnitř jedné složky, ostatní dvojice jsou proti klasickým referencím na týchž listinách. Anglická větev: anglická instrukce a anglické názvy; česká větev: česká instrukce a české názvy (kde jsou), persona a aspekty v profilu jsou české v obou větvích.

Vzorkovaný protokol: skrytý poslední nákup proti 100 náhodným nekoupeným produktům, stejným jako u klasických metod, náhodný tip 9,9 % v top 10. Úplný katalog: proti všem 18213 produktům, náhodný tip 0,1 %. Referenční metody `als_cf` a `popularity` jsou spočítány na týchž zákaznících a týchž listinách. Volání: ok = každý identifikátor právě jednou; partial = chybějící identifikátory doplněny na konec v pořadí promptu; failed = neznámý nebo opakovaný identifikátor, chyba poskytovatele nebo časový limit (zákazník bez odpovědi se řadí náhodně).

Tabulka 1 – Zásahy v top 10, metoda × větev × protokol, s referencí na týchž listinách

| metoda | poskytovatel / model / úroveň | větev | protokol | zákazníků | volání ok / partial / failed (skrytý mezi vynechanými) | zásahy | HR@10 (95% IS) | NDCG@10 | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rank_candidates` | agy / gemini-3.8-flash / medium | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 94 / 6 / 0 (0) | 64 / 100 | 64,0 % (54,2 %–72,7 %) | 0,3833 | 28 | 34 |
| `rank_candidates` | agy / gemini-3.8-flash / medium | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 90 / 10 / 0 (0) | 64 / 100 | 64,0 % (54,2 %–72,7 %) | 0,3995 | 28 | 34 |
| `rerank_als` | codex / gpt-5.5 / low | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 49 / 51 / 0 (1) | 57 / 100 | 57,0 % (47,2 %–66,3 %) | 0,3941 | 28 | — |
| `rerank_als` | codex / gpt-5.5 / low | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 58 / 42 / 0 (0) | 54 / 100 | 54,0 % (44,3 %–63,4 %) | 0,3732 | 28 | — |
| `rerank_als_with_profile` | codex / gpt-5.5 / low | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 50 / 50 / 0 (0) | 51 / 100 | 51,0 % (41,3 %–60,6 %) | 0,338 | 28 | — |
| `rerank_als_with_profile` | codex / gpt-5.5 / low | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 49 / 51 / 0 (0) | 48 / 100 | 48,0 % (38,5 %–57,7 %) | 0,3469 | 28 | — |
| `describe_and_retrieve` | agy / gemini-3.8-flash / medium | anglická větev | úplný katalog | 100 | 100 / 0 / 0 (0) | 2 / 100 | 2,0 % (0,5 %–7,0 %) | 0,0059 | 3 | 0 |
| `describe_and_retrieve` | agy / gemini-3.8-flash / medium | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 100 / 0 / 0 (0) | 25 / 100 | 25,0 % (17,5 %–34,3 %) | 0,148 | 28 | 34 |
| `describe_and_retrieve` | agy / gemini-3.8-flash / medium | česká větev | úplný katalog | 100 | 100 / 0 / 0 (0) | 3 / 100 | 3,0 % (1,0 %–8,5 %) | 0,0156 | 3 | 0 |
| `describe_and_retrieve` | agy / gemini-3.8-flash / medium | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | 100 | 100 / 0 / 0 (0) | 21 / 100 | 21,0 % (14,2 %–30,0 %) | 0,1231 | 28 | 34 |
| `rerank_als_top200` | codex / gpt-5.5 / low | anglická větev | úplný katalog | 44 | 5 / 39 / 0 (0) | 11 / 44 | 25,0 % (14,6 %–39,4 %) | 0,1431 | 6 | — |
| `rerank_als_top200` | codex / gpt-5.5 / low | česká větev | úplný katalog | 44 | 5 / 39 / 0 (1) | 10 / 44 | 22,7 % (12,8 %–37,0 %) | 0,1294 | 6 | — |

Tabulka 2 – Párové rozdíly na týchž zákaznících (zásah v top 10; oboustranný znaménkový test nad neshodnými páry)

| metoda | větev | protokol | proti | zásahy proti | zásahy metoda | rozdíl | jen metoda | jen proti | p (znaménkový) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rank_candidates` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 64 | +36 | 41 | 5 | 0,0 |
| `rank_candidates` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `popularity` | 34 | 64 | +30 | 44 | 14 | 0,0 |
| `rank_candidates` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 64 | +36 | 40 | 4 | 0,0 |
| `rank_candidates` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `popularity` | 34 | 64 | +30 | 45 | 15 | 0,0 |
| `rerank_als` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 57 | +29 | 32 | 3 | 0,0 |
| `rerank_als` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 54 | +26 | 28 | 2 | 0,0 |
| `rerank_als_with_profile` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 51 | +23 | 28 | 5 | 0,0 |
| `rerank_als_with_profile` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `rerank_als` | 57 | 51 | -6 | 3 | 9 | 0,146 |
| `rerank_als_with_profile` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 48 | +20 | 24 | 4 | 0,0 |
| `rerank_als_with_profile` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `rerank_als` | 54 | 48 | -6 | 2 | 8 | 0,109 |
| `describe_and_retrieve` | anglická větev | úplný katalog | `als_cf` | 3 | 2 | -1 | 2 | 3 | 1,0 |
| `describe_and_retrieve` | anglická větev | úplný katalog | `popularity` | 0 | 2 | +2 | 2 | 0 | 0,5 |
| `describe_and_retrieve` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 25 | -3 | 17 | 20 | 0,743 |
| `describe_and_retrieve` | anglická větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `popularity` | 34 | 25 | -9 | 19 | 28 | 0,243 |
| `describe_and_retrieve` | česká větev | úplný katalog | `als_cf` | 3 | 3 | +0 | 3 | 3 | 1,0 |
| `describe_and_retrieve` | česká větev | úplný katalog | `popularity` | 0 | 3 | +3 | 3 | 0 | 0,25 |
| `describe_and_retrieve` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `als_cf` | 28 | 21 | -7 | 16 | 23 | 0,337 |
| `describe_and_retrieve` | česká větev | vzorkovaný (1 skrytý + 100 náhodných nekoupených) | `popularity` | 34 | 21 | -13 | 15 | 28 | 0,066 |
| `rerank_als_top200` | anglická větev | úplný katalog | `als_cf` | 6 | 11 | +5 | 6 | 1 | 0,125 |
| `rerank_als_top200` | česká větev | úplný katalog | `als_cf` | 6 | 10 | +4 | 6 | 2 | 0,289 |

Tabulka 3 – Co model napsal jako příští nákup vedle toho, co zákazník skutečně koupil (metoda popíše a katalog najde; první zákazníci každé větve)

| větev | zákazník | skutečný příští nákup | tři řádky modelu |
| --- | --- | --- | --- |
| anglická větev | 2 | Sabrent 4 Port Portable USB 2.0 Hub (9.5" cable) for Ultra Book, MacBook Air, Windows 8 Ta | SanDisk Ultra 32GB Class 10 MicroSDHC Memory Card · Hardwire Kit with Mini USB for Car Dash Cam · Car Rearview Mirror Mount Holder for DB POWER Dash Cam |
| anglická větev | 3 | Swage Sport Bluetooth Headphones - Bluetooth V4.0 Perfect for Sports - Lightweight Sport B | AmazonBasics Digital Optical Audio Toslink Cable - 6 Feet (1.8 Meters) · Livescribe Dot Paper Notebook for Livescribe 3 Smartpen · Sony NP-BX1 Rechargeable Battery Pack for Sony Handycam |
| anglická větev | 4 | Denon HEOS 3 Wireless Speaker | Western Digital Red 3TB 3.5-Inch NAS Internal Hard Drive · Creative Sound Blaster Roar Travel Carry Case · SanDisk Ultra 32GB MicroSDHC Memory Card with Adapter |
| česká větev | 2 | Přenosný 4portový USB 2.0 Hub Sabrent (kabel 9,5") pro Ultra Book, MacBook Air, tablet s W | Paměťová karta Transcend 32GB microSDHC Class 10 s adaptérem pro autokamery · Přísavný držák na čelní sklo pro autokameru DBPOWER s otočným kloubem · Sada náhradních hrotů pro pero grafického tabletu Ugee M708 (10 ks) |
| česká větev | 3 | Swage Sport Bluetooth sluchátka - Bluetooth V4.0 ideální pro sport - Lehká sportovní Bluet | Zápisník s tečkovaným papírem Livescribe Dot Paper pro pero Livescribe 3 · Digitální optický audio kabel Toslink pro soundbar, délka 2 m · Interní SSD disk Samsung 840 EVO 250 GB 2,5" SATA III |
| česká větev | 4 | Bezdrátový reproduktor Denon HEOS 3 | Interní pevný disk Western Digital Red 3TB 3,5" SATA III pro NAS úložiště · Cestovní ochranné pouzdro pro reproduktor Creative Sound Blaster Roar · Tvrzené ochranné sklo pro Apple iPhone 5/5S s tvrdostí 9H |

Zdrojová data po řádcích: `attachments/uc04-model-methods.csv`; každé volání doslova: `calls/` ve složce běhu.
