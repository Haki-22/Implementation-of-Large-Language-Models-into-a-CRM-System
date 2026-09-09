# Odvozený profil OCEAN (příloha, generováno)

Vygenerováno dne 2026-09-06 ze složek běhů `ucs/uc01_personalization/snapshots/runs/2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-20-contacts/`, `ucs/uc01_personalization/snapshots/runs/2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-100-contacts/`, `ucs/uc01_personalization/snapshots/runs/2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-305-contacts/` a ze snímku `ucs/uc01_personalization/snapshots/ocean_inferred.json`, který je z nich zmrazen. Profil je odhad z textu anglických recenzí, ne změřená osobnost.

Tabulka 1 – Běh `2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-20-contacts`

| klíč | hodnota | význam |
| --- | --- | --- |
| `date` | 2026-09-06 | den běhu |
| `model` | agy / gemini-3.8-flash / medium | provider, model, úroveň uvažování |
| `prompt_version` | 1.2.0 | verze promptu (BFI-2, výstup vynucený schématem) |
| `targets` | 20 | cílených kontaktů |
| `ok` | 20 | profilů uvnitř 1 až 5 |
| `failed` | 0 | selhaných volání |
| `skipped` | 0 | přeskočeno (bez recenzí) |
| `wall_seconds` | 113.2 | stěna při souběhu 4 |
| `calls_per_minute` | 10.6 | propustnost |
| `median_prompt_chars` | 9760 | medián znaků recenzí v promptu |
| `reviews_cap` | 15 × 600 | recenzí na kontakt × znaků na recenzi |

Tabulka 2 – Běh `2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-100-contacts`

| klíč | hodnota | význam |
| --- | --- | --- |
| `date` | 2026-09-06 | den běhu |
| `model` | agy / gemini-3.8-flash / medium | provider, model, úroveň uvažování |
| `prompt_version` | 1.2.0 | verze promptu (BFI-2, výstup vynucený schématem) |
| `targets` | 100 | cílených kontaktů |
| `ok` | 100 | profilů uvnitř 1 až 5 |
| `failed` | 0 | selhaných volání |
| `skipped` | 0 | přeskočeno (bez recenzí) |
| `wall_seconds` | 483.8 | stěna při souběhu 4 |
| `calls_per_minute` | 12.4 | propustnost |
| `median_prompt_chars` | 9861 | medián znaků recenzí v promptu |
| `reviews_cap` | 15 × 600 | recenzí na kontakt × znaků na recenzi |

Tabulka 3 – Běh `2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-305-contacts`

| klíč | hodnota | význam |
| --- | --- | --- |
| `date` | 2026-09-06 | den běhu |
| `model` | agy / gemini-3.8-flash / medium | provider, model, úroveň uvažování |
| `prompt_version` | 1.2.0 | verze promptu (BFI-2, výstup vynucený schématem) |
| `targets` | 305 | cílených kontaktů |
| `ok` | 305 | profilů uvnitř 1 až 5 |
| `failed` | 0 | selhaných volání |
| `skipped` | 0 | přeskočeno (bez recenzí) |
| `wall_seconds` | 1480.1 | stěna při souběhu 4 |
| `calls_per_minute` | 12.4 | propustnost |
| `median_prompt_chars` | 9776 | medián znaků recenzí v promptu |
| `reviews_cap` | 15 × 600 | recenzí na kontakt × znaků na recenzi |

Tabulka 4 – Rysy BFI-2 po skupinách (průměr ± sd na škále 1 až 5)

| skupina | n | otevřenost | svědomitost | extraverze | přívětivost | neuroticismus |
| --- | --- | --- | --- | --- | --- | --- |
| A | 300 | 4.12 ± 0.18 | 4.21 ± 0.23 | 3.36 ± 0.27 | 3.68 ± 0.41 | 2.55 ± 0.44 |
| B | 50 | 4.12 ± 0.20 | 4.30 ± 0.18 | 3.31 ± 0.36 | 3.67 ± 0.36 | 2.51 ± 0.42 |
| C | 75 | 4.17 ± 0.13 | 4.23 ± 0.22 | 3.30 ± 0.31 | 3.62 ± 0.37 | 2.63 ± 0.44 |
| celkem | 425 | 4.13 ± 0.17 | 4.22 ± 0.23 | 3.35 ± 0.29 | 3.67 ± 0.40 | 2.56 ± 0.44 |

Tabulka 5 – Shoda s během z 29. 5. 2026 (Gemini 3.1 Pro) na společných lidech

| klíč | hodnota | význam |
| --- | --- | --- |
| `overlap` | 62 | lidí s profilem v květnovém i novém běhu |
| `O:mean_abs_diff` | 0.2 | otevřenost, průměrná absolutní odchylka nový − květen |
| `O:mean_diff` | -0.16 | otevřenost, průměrná odchylka nový − květen (znaménko) |
| `C:mean_abs_diff` | 0.29 | svědomitost, průměrná absolutní odchylka nový − květen |
| `C:mean_diff` | -0.28 | svědomitost, průměrná odchylka nový − květen (znaménko) |
| `E:mean_abs_diff` | 0.24 | extraverze, průměrná absolutní odchylka nový − květen |
| `E:mean_diff` | -0.17 | extraverze, průměrná odchylka nový − květen (znaménko) |
| `A:mean_abs_diff` | 0.21 | přívětivost, průměrná absolutní odchylka nový − květen |
| `A:mean_diff` | -0.12 | přívětivost, průměrná odchylka nový − květen (znaménko) |
| `N:mean_abs_diff` | 0.24 | neuroticismus, průměrná absolutní odchylka nový − květen |
| `N:mean_diff` | 0.18 | neuroticismus, průměrná odchylka nový − květen (znaménko) |
| `max_abs_diff` | 0.75 | největší odchylka jednoho rysu |

