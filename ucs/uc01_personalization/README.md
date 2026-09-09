# UC-01 — personalised Czech outreach

One contact, one message brief, one level: the brief rewritten for that person in
correct Czech. The experiment asks whether a model given explicit customer data produces
grammatically correct Czech personalisation and uses the supplied facts. It checks
the vocative (the form used to address someone), informal/formal address (Ty/Vy),
and gender agreement against a simple mail-merge baseline. Nobody receives the messages, so the evidence is the text itself: the same
person, the same brief, one message per level, read side by side, plus the rule
validator and two lightweight metrics over the same messages.

Everything UC-01 reads comes from `substrate/snapshots/substrate.db`; nothing is
generated unless asked, and no model is called unless `THESIS_LLM_CALLS` (or
`--force-llm`) says so. Levels 0 and 1 call no model at all.

## The ladder

| level | name | adds to the prompt | model |
| --- | --- | --- | --- |
| L0 | generic | nothing: the brief as written (the zero point) | no |
| L1 | merge | stored greeting + a Ty/Vy swap table + four gender words, Python only | no |
| L2 | morphology | greeting, gender, Ty/Vy; the model rewrites the text for agreement | yes |
| L3a | linguistic | + the customer's frequent words and a sample of their own writing | yes |
| L3b | purchases | + the newest purchases (product, category, date) | yes |
| L3c | reviews | + the newest review headlines | yes |
| L3d | role | + job title and employer (B2B contacts) | yes |
| L3 | behaviour | + all of the above | yes |
| L4 | aspects | L3 + what the customer praises / criticises (UC-04 aspects) | yes |
| L5 | psychographic | L3 + an inferred Big Five personality profile (OCEAN), five scores | yes |
| L6a | recommendations | L5 + UC-04's recommended products with a Czech reason | yes |
| L6b | topics | L5 + UC-04's interest themes | yes |
| L6c | lifecycle | L5 + the lifecycle stage | yes |
| L6d | pricing | L6a + the price line (`pricing.py`): the best recommendation at list price, the lowest-ranked priced one with 15 % off, the disclosure sentence verbatim; the rules judge checks the numbers | yes |
| L6 | hyper | L5 + all three | yes |

The arms (a–d) measure one signal alone next to the rung below them; the plain
rung combines them and the rungs above build on it. A contact that lacks an
enrichment a level needs is **skipped** with the missing slot recorded, never
called. Identity gaps never skip: a row without a stored greeting, gender or
formality runs every level, the prompt says what is unknown (the model builds
the vocative from the name, keeps the template's forms otherwise), L1 gives
what a mail merge would ("Dobrý den" / "Ahoj <first name>"), and the judge
checks only what is stored.
The prompt is composed per level from one shared block of rules plus one rule
and one line per slot (`prompts.py`); `PROMPT_VERSION` is written into every
generated row.

## Run a message or an evaluation

Complete the [root setup](../../README.md#quickstart). Run commands from the repository root; paths in the package inventory below are relative to this UC. The examples are alternatives, not one script. Replace angle-bracket placeholders before running a command.

`pick --force` replaces the saved selection. `evaluate` refreshes metrics in an existing run; `card` refreshes the published summary and attachments. New generation and judge passes create separate run folders. Use a disposable copy if you want to preserve the supplied evidence byte for byte.

```bash
python -m ucs.uc01_personalization status                              # what is in place; no model
python -m ucs.uc01_personalization pick --force                        # who the runs are for -> snapshots/picks/uc01-personalization-20-level.json
python -m ucs.uc01_personalization generate --contact 4 --brief 1 --level 1              # L1, no model
python -m ucs.uc01_personalization generate --contact 4 --brief 1 --level 3a --provider mock --show-prompt
python -m ucs.uc01_personalization run --levels 0,1                    # the no-model rungs over the pick
python -m ucs.uc01_personalization run --levels all --provider codex --model gpt-5.6-terra --tier low --force-llm --reuse <run-id>,<run-id>  # identical calls of earlier folders (a smoke, a failed run) are copied, the rest sent
python -m ucs.uc01_personalization run --levels all --provider mock    # plumbing check, no spend
python -m ucs.uc01_personalization run --levels all --provider codex --force-llm   # live calls; L0/L1 remain local
python -m ucs.uc01_personalization evaluate <run-id>                   # LSM + vocabulary overlap; no model
python -m ucs.uc01_personalization judge <run-id> --level 3 --judges codex,agy --arbiter codex:-:high --force-llm  # the judge cascade over a finished run: 2 calls/message + arbitrations
python -m ucs.uc01_personalization judge <run-id> --level 2 --judges codex,agy --arbiter codex:-:high --force-llm  # explicit judges
python -m ucs.uc01_personalization judge <run-id> --level 1 --judges codex --contacts 11,2 --briefs 1 --force-llm  # a subset (smoke)
python -m ucs.uc01_personalization faithfulness --provider codex --force-llm             # 2 calls per contact
python -m ucs.uc01_personalization report <run-id>                     # the per-level table + every judge folder
python -m ucs.uc01_personalization card                                  # the one-page card eval/RESULTS.md + attachments/uc01-{ladder,faithfulness}.{csv,md} from the runs of record; no model
python -m ucs.uc01_personalization.judge_testset --calibrate           # the rule validator's recall
python -m ucs.uc01_personalization.ocean_inference infer --sample model-arms-100 --pick uc01-personalization-20-level --previous --provider mock  # targets by rule, offline plumbing
python -m ucs.uc01_personalization.ocean_inference infer --sample model-arms-100 --pick uc01-personalization-20-level --previous --limit 20 --provider agy --model gemini-3.8-flash --tier medium --force-llm  # 1 call per contact, live calls
python -m ucs.uc01_personalization.ocean_inference freeze --runs <run-id>   # run folder(s) -> snapshots/ocean_inferred.json, then rebuild the database
python -m ucs.uc01_personalization.ocean_inference attachment          # attachments/ocean-inference.{csv,md} from the run folders the snapshot names
```

`generate` is the unit: one contact, one brief, one level, with the free rules
judge (`--judges rules` by default, `none`). `run` only loops it over a pick
and writes one folder per run under `snapshots/runs/<run-id>/` (config, the
pick used, every message with its prompt, a flat CSV, a per-level summary). A
generation run gets a new folder. The model judges are a second pass: `judge <run-id>`
reads the run's messages and writes its own `judge-<id>/` folder beside them,
so one run can be judged again with other judges. The frontend calls the same
`generate()` for live generation.

## Who the runs are for

Not a census: a **reading set** of 16 contacts, four per cell of formality x
gender: three linked contacts (a clean row with Czech text and a purchase
history; every linked contact carries an inferred OCEAN profile since 2026-09-06
and UC-04 writes its outputs for whoever is picked, so every model level can
run) and one prospect with no history at all (only L0 to L2 run). The current selection replaced an earlier full/partial split on 2026-09-07:
withholding data from a partial contact repeated a lower rung of a full one. Within
a kind: a matching-gender purchase history first, then the lowest id; prospects
by id. Beside the cells, 4 defective rows (no stored greeting, unknown gender
or formality: the error table), and three briefs named in `LADDER_BRIEFS`
(invitation `seasonal_sale_launch`, upsell `personal_recommendation`, follow-up
`review_request_with_reward`), chosen so that every enrichment has a place. Not
every rung runs on every brief: the evidence per rung is a diff (same contact,
same brief, one more field), so the tiers the assignment names (L2, L3, L5, L6)
run on all three briefs and each single-field arm runs on the one brief where
its field has a place (own words and role in the invitation; purchases, reviews,
aspects, recommendations, topics, pricing in the upsell; lifecycle in the
follow-up). That map is
`LEVEL_BRIEF_CATEGORIES` in `picker.py`, written into the pick as
`briefs_by_level`; `--briefs` overrides it for every level. The rule and the
resulting ids are the pick file; every run copies it, and every result row
carries the contact's tier. `--contact` / `--contacts` run anyone else.

## How a message is judged

Two kinds of judge, in a fixed order: a **script rule** that reads what the contact
row stores (free, always first) and **model judges** that read the whole text (a
second pass over a saved run, or after generation in the GUI). The judges and the
routing live in `judge.py`, the pass over a run in `judge_run.py`. The symbol names below identify the implementation without relying on line numbers.

### 1. The script rule — `judge.py::validate_rules`, free

| Check | Failure code | What it reads | Symbols |
| --- | --- | --- | --- |
| greeting | `VOCATIVE_MISMATCH`, `DUPLICATE_GREETING` | the message opens with the stored `name_vocative`, once (the brief's leading emoji and symbols are skipped, letters are not; 2026-09-07) | `validate_rules` |
| pricing (L6d) | `PRICING_MISMATCH` | both prices, the discount and the disclosure sentence of `pricing.offer` are in the message, whitespace and case ignored; only when the level carries the `pricing` slot | `pricing_check`, `pricing.expected_in_message` |
| register | `REGISTER_MISMATCH` | no pronoun of the opposite register | `_FORMAL_MARKERS`, `_INFORMAL_MARKERS`, `_register_consistent` |
| gender | `GENDER_MISMATCH` | the four sites where Czech agrees with the addressee: l-participle at the auxiliary, short predicate after it, the recipient's role noun, its adjective; plural is neutral | `_GENDER_PATTERNS`, `gender_sites` |
| leakage | `INSTRUCTION_BLEED` | instruction fragments and xml tags in the text | `_INSTRUCTION_BLEED` |

A check applies only when the row stores the field it compares against; the verdict
(`RulesVerdict`) lists the others as `unchecked` and the gender evidence as
`gender_sites`. Calibration on the 100-message set (`judge_testset.py::calibrate`,
`python -m ucs.uc01_personalization.judge_testset --calibrate`, data
`snapshots/uc01-judge-testset.json`): valid 60/60 accepted, vocative 10/10, register
10/10, combined 10/10, gender 9/10 rejected; the miss is a sender-side "jsem ráda",
outside a recipient rule. Before the gender rule: combined 9/10, gender 0/10.

### 2. One model judge call — `judge.py::judge_with_model`

| Piece | Where | What |
| --- | --- | --- |
| judge prompt | `JUDGE_SYSTEM`, `JUDGE_PROMPT_VERSION` = 1.2.0 | Czech: judge ONLY the vocative, the register and the gender; per criterion a boolean and a **verbatim span** of the message; "neposuzováno" only where the fact is not stored; several places joined with ";", no commentary |
| judge schema | `JUDGE_SCHEMA` | six required keys: `<criterion>_ok` (boolean), `<criterion>_evidence` (string) |
| arbiter prompt | `ARBITER_SYSTEM`, `ARBITER_PROMPT_VERSION` = 1.1.0 | the judge prompt plus the two prior verdicts with their spans and labels; decide from the message, not by majority; one-sentence `reason` |
| arbiter schema | `ARBITER_SCHEMA` | the judge schema plus `reason` |
| the call | `judge_with_model`, `_facts` | the facts (stored greeting or name, gender, formality) and `<zpráva>…</zpráva>` go to `utils.generation.generate_json` with the schema through the CLI's native flag; a failed call is a MALFORMED verdict, never an exception |
| span check | `span_status`, `evidence_fragments` | each span is labelled `found` (in the message, case and whitespace ignored), `missing` or `n/a`; reads quoted pieces, ";" / "," fragments and the text before a dash-explanation, because live judges quote in all three shapes |
| dodge check | `assessable_criteria` | "neposuzováno" on a criterion whose fact is stored counts as `missing` |
| the verdict | `JudgeVerdict`, `evaluate_judge_json` | booleans exactly as returned, spans labelled, status **FULL** (no span missing) / **PARTIAL** (a span missing) / **MALFORMED** (no usable booleans); `verdict` = AND of the booleans. A label never changes a boolean |

### 3. The cascade — `judge.py::Cascade`, `default_cascade`, `judge_cascade`

| Level | Judges (default) | Arbiter | Composes VALID when | Moves onward when | Onward to | Calls / message |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | one: the first of claude, agy, codex that did not write the run, tier low | – | the judge is FULL and valid | PARTIAL, MALFORMED or invalid | human | 1 |
| 2 | two: the two providers that did not write the run, tier low | – | both FULL and valid | disagreement, a PARTIAL or a MALFORMED judge | human | 2 |
| 3 | as level 2 | the writer's provider at tier `high` (`ARBITER_TIER`), no stronger model | both FULL and valid, or the arbiter FULL and valid | the pair does not compose → arbiter; the arbiter PARTIAL, MALFORMED or invalid → human | arbiter, then human | 2, +1 on escalation |

The script rule runs before every level: a failure is HUMAN at once and costs no call.
CLI defaults follow the writer (`JUDGE_ORDER`): a codex-written run gets claude and
agy as judges and codex/high as arbiter. Override with
`--judges provider[:model[:tier]],…` and `--arbiter provider[:model[:tier]]`
(`JudgeSpec.parse`); the config records the resolved model ids.

The CLI defaults can select Claude. To avoid it, set every model role explicitly, as in the commands above. The GUI offers four levels: rules only, one judge, two judges, and two judges with escalation. Each model role has its own provider, model and tier selectors; Claude is blocked there. Two judges must use distinct providers, while the arbiter can reuse a provider. A green, orange or red dot shows a valid, partial or invalid result beside the corresponding stage; unavailable/error states remain distinct. A stage result is not the same as the final VALID/PARTIAL/HUMAN routing decision. GUI rules-only mode corresponds to generation with `--judges rules`, not CLI `judge --level 0`.

### 4. Outcomes — `judge.py::decide`, the routing table as a pure function

| Final | Meaning | `reason` values |
| --- | --- | --- |
| `VALID` | accepted; the trail stays in `verdicts.jsonl` | `judge_valid`, `judges_agree_valid`, `arbiter_valid` |
| `PARTIAL` | every judge in line said ok, but a span was missing: **a human verifies** | `judge_partial_evidence`, `arbiter_partial_evidence` |
| `HUMAN` | **a human decides** | `rules:<codes>`, `judge_invalid`, `judges_agree_invalid`, `judges_disagree`, `judge_malformed`, `arbiter_invalid`, `arbiter_malformed` |

Nothing is auto-rejected or regenerated. Helpers: `decide_single` (the last judge in line), `decide_pair`, `onward_reason`.

### 5. The pass over a run and the human sheet — `judge_run.py`

```bash
python -m ucs.uc01_personalization judge <run-id> --level 3 --judges codex,agy --arbiter codex:-:high --force-llm            # explicit roles; no Claude
python -m ucs.uc01_personalization judge <run-id> --level 1 --judges codex --contacts 11,2 --briefs 1 --force-llm   # a subset
python -m ucs.uc01_personalization judge <run-id> --level 2 --judges codex,agy --arbiter codex:-:high --force-llm
```

`__main__.py::cmd_judge` → `judge_run.judge_run`: reads the run's
`messages.jsonl` (`load_run_messages`; skipped and failed rows have no text),
loads each contact, runs `judge_cascade` per message at concurrency 4 and writes
`snapshots/runs/<run-id>/judge-<id>/`:

| File | Written by | Content |
| --- | --- | --- |
| `config.json` | `judge_run` | level, judges and arbiter with resolved model ids and tiers, prompt versions, subset, the switch state, calls, seconds |
| `verdicts.jsonl` | `judge_run` | one trail per message: rules, `judges[]`, `arbiter`, `final`, `reason` |
| `summary.json` | `summarise` | per generation level and in total: VALID / PARTIAL / HUMAN, reasons, `judge_agreement` (both FULL and the same booleans), `judge_boolean_agreement` (the booleans alone), arbitrations, calls by provider |
| `human-review.md` | `human_sheet` | "To decide (HUMAN)" then "To verify (PARTIAL)": the message, the facts, the rules result, one table row per verdict with spans and labels, the arbiter's reason, an empty "Human verdict" line |

The run's own files are never touched; judging the run again is another `judge-<id>/`.
`report <run-id>` prints every judge folder's summary. The "Human verdict" lines are blank review fields, not evidence that human review has already taken place.

### 6. What has run

- Rules: calibrated 2026-09-05 as above.
- Cascade: live smoke 2026-09-05 on three L2 messages, levels 1–3 and the arbiter,
  27 calls covering the exercised paths; after the span-check fix and prompt 1.2.0, level 3
  composed 3/3 VALID with both judges FULL and no arbitration. Not yet seen on a
  wrong message. A complete model-judge pass over the ladder is not included in the run of record.
- Ladder of record 2026-09-07: `snapshots/runs/2026-09-07-uc01-personalization-20-level-codex-gpt-5.6-terra-low-all/` (Codex gpt-5.6-terra low, prompt 2.4.1, pick `uc01-personalization-20-level`): 540 messages, 339 model calls (41 reused from the smokes), 0 errors, rules judge 339/339 on every model level incl. 6d; `evaluate` run. The model was chosen by seven `smoke-*` runs on contacts 2, 4 and 11 (luna low, terra low, terra medium; prompts 2.2.0 to 2.4.1): every judge failure was read by hand against the stored prompt, one was the judge's (leading emoji), two the prompt's (the template's Vy at L5/L6), the rest the model's (luna drops the greeting now and then). Outputs for UC-01 (UC-04, `for-uc01`): luna low, 80/80 reasons grounded.
- Offline: the mock provider answers the judge schema with a FULL valid verdict quoting
  the message's first line (`utils/generation/mock.py::_judge_verdict`), so `judge`
  runs without a model for plumbing.
- Tests: `tests/ucs/uc01_personalization/test_judge.py` (rules, calibration),
  `test_judge_cascade.py` (span check, statuses, the routing table per level, the
  cascade with faked judges, the pass over a run, the human sheet).

## Structure

```
uc01_personalization/
├── __init__.py         package docstring; re-exports generate(), Generation, LADDER, LEVELS (the frontend imports these)
├── data.py             every read from substrate.db: contact, brief, enrichment
├── prompts.py          the Czech prompt text: shared rules + one rule and one line per slot
├── levels.py           the ladder: what each level needs; L0 / L1 without a model
├── judge.py            the rules validator + the model judges: span check, cascade levels 1-3, routing table
├── judge_run.py        the second pass over a run folder -> snapshots/runs/<run-id>/judge-<id>/ (+ human-review.md)
├── generate.py         the single call: generate(contact, brief, level) -> Generation
├── picker.py           the selection rule -> snapshots/picks/<name>.json
├── runner.py           loop a pick over briefs x levels -> snapshots/runs/<run-id>/
├── metrics.py          LSM, overlap, OCEAN faithfulness
├── judge_testset.py    the 100-message calibration set builder + --calibrate
├── ocean_inference.py  OCEAN profiles from the English reviews: targets by rule (UC-04's sample, the pick, today's snapshot), one call per contact into a run folder; freeze -> the snapshot
├── __main__.py         the command line above
└── snapshots/          README.md; picks/; runs/ (message runs and OCEAN inference runs); ocean_inferred.json (the profiles the database build loads);
                        uc01-judge-testset.json (the calibration set)
```

The UC-04 → UC-01 handoff file (`uc04_to_uc01_handoff.json`) is UC-04's product
(`ucs/uc04_matchmaker/results/uc04_to_uc01_handoff.json`, produced by `outputs_for_uc01/` and defined in `handoff.py`); the database build
loads it into `uc_recommendations` / `uc_topics` / `uc_aspects`.

## Outputs

The September 7 ladder record does not contain a database hash. Current runners record one for new runs, but a hash computed now cannot establish which database produced that earlier record.

- `snapshots/picks/uc01-personalization-20-level.json` — the pick (committed; provenance of who
  was generated for). Drawn on 2026-09-07 by the selection rule described above (3 linked + 1 prospect per
  cell, 4 defective rows, named briefs). It replaced `reading-16` of 2026-09-04, whose rule
  (data tiers, "inferred first", "has a UC-04 output") had stopped describing the database once
  every linked contact had an inferred profile and UC-04 wrote its outputs for the pick; the
  runs made with `reading-16` (L0–L1, L2) were deleted with it, nothing reported rests on them.
  UC-04's sample `model-arms-100` was drawn from `reading-16` and deliberately not redrawn
  (its members are marked in the sample file).
- `snapshots/runs/<run-id>/` — one folder per run: `config.json`, `pick.json`,
  `messages.jsonl`, `results.csv`, `summary.json`, and after `evaluate`
  `metrics.csv` + `metrics-summary.json`. Committed when a run backs a number in the thesis.
- `snapshots/runs/<date>-ocean-inference-<provider>-<model>-<tier>-<N>-contacts/` — one folder per
  OCEAN inference batch: `config.json` (resolved model, prompt version and text, schema, caps, database hash),
  `targets.json` (who and by which rule), `responses/<reviewer>.json` (raw answer + parsed profile or error),
  `status.csv`, `profiles.json`, `summary.json`, `RESULTS.md`. The provenance of every inferred profile.
- `snapshots/ocean_inferred.json` — the inferred OCEAN profiles the database build loads, written by `freeze`
  from run folders; every entry names its run. Who is inferred for: UC-04's model-arm sample, the pick's
  linked contacts, and everyone the previous snapshot held (English reviews only; a reading of review
  text, not a measured personality).
- `snapshots/uc01-judge-testset.json` — the 100-message calibration set (60 valid, 40 invalid in four kinds) behind the recall figures above.

Tests: `pytest tests/ucs/uc01_personalization/ -q` (the database-backed ones skip without `substrate.db`).
