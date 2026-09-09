# UC-04 model methods — 2026-09-07-model-methods-rank-candidates-describe-and-retrieve-codex-gpt-5.6-terra-low-en-cs-100-customers-3

Sample `model-arms-100`: 100 customers; provider codex / gpt-5.6-terra / low (CLI codex-cli 0.153.4); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). 'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right answer, which then lands at the end of the list.

## `rank_candidates` — Model ranks the candidates alone

whole history + the 101 sampled candidates in a seeded random order; the model returns the full permutation; no classical input. ML input: none.

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | 100 | 46 / 54 / 0 (99 reused) | 46 / 100 | 46.0 % (36.6 %–55.7 %) | 0.3085 | 0.2612 | 12.3 | 28 / 100 | 34 / 100 |
| cs | sampled | 100 | 48 / 52 / 0 (97 reused) | 45 / 100 | 45.0 % (35.6 %–54.8 %) | 0.2946 | 0.2466 | 11.1 | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | sampled | `als_cf` | 28 | 46 | +18 | 28 | 10 | 0.005 |
| en | sampled | `popularity` | 34 | 46 | +12 | 32 | 20 | 0.126 |
| cs | sampled | `als_cf` | 28 | 45 | +17 | 28 | 11 | 0.009 |
| cs | sampled | `popularity` | 34 | 45 | +11 | 31 | 20 | 0.161 |

## `describe_and_retrieve` — Model describes the next purchase, the catalogue index retrieves it

whole history -> three listing lines for the next purchase -> multilingual-e5 query vectors against the cached catalogue vectors; score = best cosine over the three lines. ML input: the dense e5 index of the catalogue (the dense_e5 arm's cached vectors).

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | full | 100 | 100 / 0 / 0 (100 reused) | 0 / 100 | 0.0 % (0.0 %–3.7 %) | 0.0000 | 0.0000 | — | 3 / 100 | 0 / 100 |
| en | sampled | 100 | 100 / 0 / 0 (100 reused) | 29 / 100 | 29.0 % (21.0 %–38.5 %) | 0.1705 | 0.1342 | — | 28 / 100 | 34 / 100 |
| cs | full | 100 | 100 / 0 / 0 (100 reused) | 0 / 100 | 0.0 % (0.0 %–3.7 %) | 0.0000 | 0.0000 | — | 3 / 100 | 0 / 100 |
| cs | sampled | 100 | 100 / 0 / 0 (100 reused) | 27 / 100 | 27.0 % (19.3 %–36.4 %) | 0.1684 | 0.1380 | — | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | full | `als_cf` | 3 | 0 | -3 | 0 | 3 | 0.25 |
| en | full | `popularity` | 0 | 0 | +0 | 0 | 0 | 1.0 |
| en | sampled | `als_cf` | 28 | 29 | +1 | 16 | 15 | 1.0 |
| en | sampled | `popularity` | 34 | 29 | -5 | 21 | 26 | 0.56 |
| cs | full | `als_cf` | 3 | 0 | -3 | 0 | 3 | 0.25 |
| cs | full | `popularity` | 0 | 0 | +0 | 0 | 0 | 1.0 |
| cs | sampled | `als_cf` | 28 | 27 | -1 | 16 | 17 | 1.0 |
| cs | sampled | `popularity` | 34 | 27 | -7 | 20 | 27 | 0.382 |

What the model wrote beside what the customer really bought next (first customers per branch):

- en, customer 2, bought next: `B00L2442H0` — model: MicroSD card for dash cam video storage | Car USB charger with dual USB ports | Bluetooth hands-free car kit with 3.5 mm AUX compatibility
- en, customer 3, bought next: `B00JWV1LP6` — model: HDMI cable with Audio Return Channel for a 2.1-channel sound bar | Bluetooth subwoofer compatible with Sharp HT-SB602 sound bar | Wall-mount bracket for Sharp HT-SB602 sound bar
- en, customer 4, bought next: `B00KJJW36G` — model: MicroSDXC memory card for action cameras and dash cams | Portable Bluetooth speaker with NFC and aptX | Dual-band USB Wi-Fi adapter for Windows and Mac
- cs, customer 2, bought next: `B00L2442H0` — model: Paměťová karta microSDHC 32 GB Class 10 pro automobilovou kameru | Držák automobilové kamery na čelní sklo s přísavkou | Autonabíječka USB s vysokým výkonem pro napájení DVR kamery
- cs, customer 3, bought next: `B00JWV1LP6` — model: Bezdrátová Bluetooth sluchátka přes uši s integrovaným mikrofonem a dlouhou výdrží baterie | Vysokorychlostní HDMI kabel s Ethernetem pro domácí kino a 3D/1080p | Přenosný voděodolný Bluetooth reproduktor s NFC a dobíjecí baterií
- cs, customer 4, bought next: `B00KJJW36G` — model: Ochranné pouzdro nebo obal pro přenosný Bluetooth reproduktor Creative Sound Blaster Roar | Bluetooth audio přijímač s aptX/AAC a 3,5mm výstupem pro domácí stereo | Síťový disk NAS se dvěma pozicemi a pevnými disky pro NETGEAR ReadyNAS 102

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
