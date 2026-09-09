# UC-04 model methods — 2026-09-07-model-methods-describe-and-retrieve-agy-gemini-3.8-flash-medium-en-cs-100-customers

Sample `model-arms-100`: 100 customers; provider agy / gemini-3.8-flash / medium (CLI 1.1.27); prompt version 1.0.2; seed 42. Guessing scores 9.9 % at top 10 under the sampled protocol (1 hidden + 100 unbought) and 0.1 % under the full catalogue (18213 products). The references `als_cf` and `popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). 'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right answer, which then lands at the end of the list.

## `describe_and_retrieve` — Model describes the next purchase, the catalogue index retrieves it

whole history -> three listing lines for the next purchase -> multilingual-e5 query vectors against the cached catalogue vectors; score = best cosine over the three lines. ML input: the dense e5 index of the catalogue (the dense_e5 arm's cached vectors).

| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) | NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | full | 100 | 100 / 0 / 0 (97 reused) | 2 / 100 | 2.0 % (0.6 %–7.0 %) | 0.0059 | 0.0021 | 19.6 | 3 / 100 | 0 / 100 |
| en | sampled | 100 | 100 / 0 / 0 (97 reused) | 25 / 100 | 25.0 % (17.5 %–34.3 %) | 0.1480 | 0.1166 | 19.6 | 28 / 100 | 34 / 100 |
| cs | full | 100 | 100 / 0 / 0 (100 reused) | 3 / 100 | 3.0 % (1.0 %–8.5 %) | 0.0156 | 0.0108 | — | 3 / 100 | 0 / 100 |
| cs | sampled | 100 | 100 / 0 / 0 (100 reused) | 21 / 100 | 21.0 % (14.2 %–30.0 %) | 0.1231 | 0.0964 | — | 28 / 100 | 34 / 100 |

Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):

| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| en | full | `als_cf` | 3 | 2 | -1 | 2 | 3 | 1.0 |
| en | full | `popularity` | 0 | 2 | +2 | 2 | 0 | 0.5 |
| en | sampled | `als_cf` | 28 | 25 | -3 | 17 | 20 | 0.743 |
| en | sampled | `popularity` | 34 | 25 | -9 | 19 | 28 | 0.243 |
| cs | full | `als_cf` | 3 | 3 | +0 | 3 | 3 | 1.0 |
| cs | full | `popularity` | 0 | 3 | +3 | 3 | 0 | 0.25 |
| cs | sampled | `als_cf` | 28 | 21 | -7 | 16 | 23 | 0.337 |
| cs | sampled | `popularity` | 34 | 21 | -13 | 15 | 28 | 0.066 |

What the model wrote beside what the customer really bought next (first customers per branch):

- en, customer 2, bought next: `B00L2442H0` — model: SanDisk Ultra 32GB Class 10 MicroSDHC Memory Card | Hardwire Kit with Mini USB for Car Dash Cam | Car Rearview Mirror Mount Holder for DB POWER Dash Cam
- en, customer 3, bought next: `B00JWV1LP6` — model: AmazonBasics Digital Optical Audio Toslink Cable - 6 Feet (1.8 Meters) | Livescribe Dot Paper Notebook for Livescribe 3 Smartpen | Sony NP-BX1 Rechargeable Battery Pack for Sony Handycam
- en, customer 4, bought next: `B00KJJW36G` — model: Western Digital Red 3TB 3.5-Inch NAS Internal Hard Drive | Creative Sound Blaster Roar Travel Carry Case | SanDisk Ultra 32GB MicroSDHC Memory Card with Adapter
- cs, customer 2, bought next: `B00L2442H0` — model: Paměťová karta Transcend 32GB microSDHC Class 10 s adaptérem pro autokamery | Přísavný držák na čelní sklo pro autokameru DBPOWER s otočným kloubem | Sada náhradních hrotů pro pero grafického tabletu Ugee M708 (10 ks)
- cs, customer 3, bought next: `B00JWV1LP6` — model: Zápisník s tečkovaným papírem Livescribe Dot Paper pro pero Livescribe 3 | Digitální optický audio kabel Toslink pro soundbar, délka 2 m | Interní SSD disk Samsung 840 EVO 250 GB 2,5" SATA III
- cs, customer 4, bought next: `B00KJJW36G` — model: Interní pevný disk Western Digital Red 3TB 3,5" SATA III pro NAS úložiště | Cestovní ochranné pouzdro pro reproduktor Creative Sound Blaster Roar | Tvrzené ochranné sklo pro Apple iPhone 5/5S s tvrdostí 9H

Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: `calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`.
