# UC-01 results — personalised Czech outreach, one message per level of the ladder

Ran on: `substrate.db` (sha256 not recorded), pick `uc01-personalization-20-level` (20 contacts: 3 linked + 1 prospect per cell of formality × gender, 4 defective rows), briefs [1, 10, 26]. Every number below sits in a run folder under `snapshots/runs/` with its `config.json` (provider, resolved model and tier, prompt version, database hash) and every message with its prompts in `messages.jsonl`. Generated 2026-09-07 by `python -m ucs.uc01_personalization card`.

## 1. The ladder — `runs/2026-09-07-uc01-personalization-20-level-codex-gpt-5.6-terra-low-all/`

    540 messages requested, 459 generated       (20 contacts of pick `uc01-personalization-20-level`, briefs [1, 10, 26], 15 levels; the rest skipped for a missing input, never for a missing identity field)
    339 model calls, 41 reused, 0 errors        (codex / gpt-5.6-terra / low, prompt 2.4.1, 534 s)
    rules judge 339 / 339 on the model levels   (greeting, Ty/Vy, gender, no instruction bleed; at 6d also both prices, the discount and the disclosure sentence)

| level | name | model | requested | generated | skipped | rules | LSM | overlap | chars |
|---|---|---|---|---|---|---|---|---|---|
| 0 | generic (obecný brief) | no | 60 | 60 | 0 | 15 % | 0.526 | 0.007 | 259 |
| 1 | merge (mail merge) | no | 60 | 60 | 0 | 100 % | 0.528 | 0.007 | 272 |
| 2 | morphology (morfologie) | yes | 60 | 60 | 0 | 100 % | 0.528 | 0.007 | 275 |
| 3a | linguistic (vlastní slova) | yes | 20 | 16 | 4 | 100 % | 0.628 | 0.044 | 338 |
| 3b | purchases (nákupy) | yes | 20 | 16 | 4 | 100 % | 0.424 | 0.000 | 121 |
| 3c | reviews (recenze) | yes | 20 | 16 | 4 | 100 % | 0.416 | 0.000 | 120 |
| 3d | role (role) | yes | 20 | 7 | 13 | 100 % | 0.623 | 0.000 | 347 |
| 3 | behaviour (chování) | yes | 60 | 48 | 12 | 100 % | 0.513 | 0.046 | 263 |
| 4 | aspects (aspekty) | yes | 20 | 16 | 4 | 100 % | 0.461 | 0.019 | 134 |
| 5 | psychographic (profil OCEAN) | yes | 60 | 48 | 12 | 100 % | 0.503 | 0.043 | 241 |
| 6a | recommendations (doporučení) | yes | 20 | 16 | 4 | 100 % | 0.520 | 0.072 | 201 |
| 6b | topics (témata) | yes | 20 | 16 | 4 | 100 % | 0.453 | 0.003 | 132 |
| 6c | lifecycle (fáze vztahu) | yes | 20 | 16 | 4 | 100 % | 0.476 | 0.050 | 278 |
| 6d | pricing (cena) | yes | 20 | 16 | 4 | 100 % | 0.442 | 0.087 | 316 |
| 6 | hyper (hyperpersonalizace) | yes | 60 | 48 | 12 | 100 % | 0.504 | 0.085 | 274 |

LSM = language style matching between the message and the customer's own writing; overlap = share of the customer's frequent words in the message; L0 fails the greeting by design (the brief as written).

## 2. The model judges

No judging of the ladder run yet (`judge <run-id>`).

## 3. Faithfulness to the profile — `runs/2026-09-07-uc01-personalization-20-level-codex-gpt-5.6-terra-low-faithfulness/`

    mean responsiveness 0.506 over 12 contacts (min 0.262, max 0.654)   (1 − Jaccard of the L5 message with the real OCEAN profile against the same message with the profile mirrored around the scale's middle: the share of words that change when only the profile changes)
    24 calls, 4 contacts skipped                                        (codex / gpt-5.6-terra / low, prompt 2.4.1, brief 1; skipped = no profile or no history (prospects))

The number says how much the text moves, not whether it moves the expected way; both texts sit side by side in `faithfulness.json` for the reading pass.

Reading: with explicit signals the model kept the greeting, the register and the gender in 339 of 339 messages (the correctness claim, checked by rule, not by a model); mirroring the personality profile changes 51 % of the words of the L5 message on average (the profile is used, in which direction the reading pass says); the diff per rung (same person, same brief, one more field) is the evidence the chapter reads, not a rate.

Appendix files generated from the same folders: `attachments/uc01-ladder.{csv,md}`, `uc01-faithfulness.{csv,md}`.
