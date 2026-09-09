# DB — entity reference for the shared CRM schema

## What this is

`substrate/schema/` is the shared SQLite + SQLModel layer. Data is
synthetic-only; no real PII is used at any stage. The compiled database lives at
`substrate/snapshots/substrate.db` (gitignored, 346 MB; rebuilt in ~15 s with
`python -m substrate.pipeline.build_substrate_db --force`).

The substrate has two surfaces, and the split decides what is a table:

- **CRM content — in the database.** Everything a CRM record consists of and
  that a user or an LLM tool could ask about at run time: contacts, their notes,
  their employer, the catalogue, the purchase history, the customer's own words
  about each purchase (the reviews, English original and Czech translation), the
  operator's message briefs.
- **Evaluation inputs and results — files, not tables.** Every batch runner
  reads committed JSON snapshots and writes JSON/CSV next to the run that
  produced them, so every number in the thesis reproduces without this
  gitignored database.

Decisions of record: D-DB-1
(2026-09-03, what is CRM content) and D-DB-3 (2026-09-04, the review text is).

## Entity inventory (as of 2026-09-04)

| Entity           | Rows   | Read at run time by                                                                                                                                                     | Written at run time by  |
| ---------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `Contact`        | 500    | UC-01 (`code/cli.py`), UC-03 tools, frontend bridge                                                                                                                     | — (build only)          |
| `Note`           | 80     | UC-03 tools                                                                                                                                                             | **UC-03 `create_note` / `update_note` / `delete_note`**; rows carry `author` and `audit_seq` |
| `ChangeLog`      | 0      | UC-03 review queue (`review.py`)                                                                                                                                        | **UC-03 `update_contact` / `update_company`** (held under strict, applied otherwise) |
| `Company`        | 8      | UC-03 tools (joined into the contact record)                                                                                                                            | — (build only)          |
| `Product`        | 18 213 | frontend bridge (purchase history join)                                                                                                                                 | — (build only)          |
| `Order`          | 45 951 | frontend bridge (purchase history join)                                                                                                                                 | — (build only)          |
| `Review`         | 45 951 | UC-01 (style-match metric reads all of a contact's Czech reviews; OCEAN inference the English ones); UC-04's arena reads it for every branch (`ucs/uc04_matchmaker/data.py`, since 2026-09-06); UC-02 still parses the JSON snapshots until its own step | — (build only)          |
| `MessageBrief`   | 25     | UC-01 (`code/cli.py`), frontend bridge                                                                                                                                  | — (build only)          |
| `LifecycleStage` | 7      | prompt formatters and screens join the Czech label                                                                                                                      | — (seeded at build)     |
| `Recommendation` | 539    | UC-01 hyper level (L6); loaded from UC-04's committed handoff file, 108 contacts                                                                                        | — (build only)          |
| `Topic`          | 540    | UC-01 hyper level (L6); same source                                                                                                                                     | — (build only)          |
| `Aspect`         | 0      | UC-01 aspect level (L4); empty until UC-04 produces the per-contact aspects                                                                                             | — (build only)          |

Plus one virtual table the ORM does not model: **`uc_reviews_fts`**, an FTS5
full-text index over the four text columns of `uc_reviews`
(`substrate.constants.REVIEWS_FTS_TABLE`). It is an external-content index, so
the text is stored once, in `uc_reviews`; `MATCH` returns rowids that join back
by `id`. Diacritics are folded (`unicode61 remove_diacritics 2`), so `vyborny`
finds `výborný`; matching is by token, so `kabel*` is the form that also finds
`kabelu`. Measured on the built database: `kabel` 8 680 rows, `kabel*` 14 231,
all in milliseconds.

`Note` and `ChangeLog` are the only tables anything writes to outside the build chain, and a reviewed `ChangeLog` row may update one field of `Contact` or `Company`. `Contact.updated_at` and `Company.updated_at` are NULL after the build and stamped by every UC-03 write; a held change is applied only while the entity still carries the timestamp it had when the change was requested (`ChangeLog.entity_updated_at`).

### Review — the interaction history in prose

One row per order (`order_id` is unique): `rating`, the two `helpful` counts,
`review_date`, and the text in both languages. English is always present
(45 909 bodies, 42 have only a headline); Czech is the frozen machine
translation joined by item and present for 42 744 bodies / 42 805 headlines —
the rest is translation loss and stays NULL rather than fall back to English.
Before D-DB-3 the text lived only in the two Amazon JSON snapshots and twelve
modules across UC-01, UC-02 and UC-04 re-parsed 100 MB of it through
`pipeline/amazon_lookup.py`; measured against that route, every access pattern
the repo performs (a contact's reviews, the longest Czech body, the newest six
headlines, the last purchase per contact for leave-one-out, a text filter over
the corpus, a join with contact and product) runs 5x to 400x faster from the
table. The cost is a 346 MB gitignored file and ~5 s more at build time.

### Contact — reading the fill rates

A column short of 500 is usually design, not damage:

| column                                                         | filled          | why                                                                                                                                                                                                                                                                                         |
| -------------------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gender`, `formal`                                             | 487             | 13 of the 50 `is_clean=False` rows omit each, to trigger UC-01's guards                                                                                                                                                                                                                     |
| `name_vocative`                                                | 450             | all 50 `is_clean=False` rows omit it (`MISSING_VOCATIVE`)                                                                                                                                                                                                                                   |
| `ocean` / `ocean_source`                                       | 338             | sampled at the 70 % design rate, plus 62 inferred profiles overriding some of them                                                                                                                                                                                                          |
| `purchase_seniority`, `relationship_warmth`                    | 450             | the two CRMArena latents, drawn for every clean contact; the defective 50 carry none                                                                                                                                                                                                        |
| `email`                                                        | 477             | PII overlay presence rate 0.95                                                                                                                                                                                                                                                              |
| `full_street` / `city` / `postal_code` / `district` / `region` | 366             | one atomic address draw at rate 0.70                                                                                                                                                                                                                                                        |
| `phone`                                                        | 311             | rate 0.60                                                                                                                                                                                                                                                                                   |
| `date_of_birth`                                                | 99              | rate 0.20 — every contact has a real age behind it, few CRMs know the birthday                                                                                                                                                                                                              |
| `bank_account` / `iban`                                        | 42 / 19         | rates 0.10 / 0.05 — sparse identifiers, as in a real CRM extract                                                                                                                                                                                                                            |
| `company_id` / `title`                                         | 231 / 132       | only B2B contacts carry an affiliation                                                                                                                                                                                                                                                      |
| `frequent_words` / `prior_interactions` / `style_excerpt`      | 411 / 411 / 410 | the three prompt digests, derived from the contact's Czech reviews at build time; NULL for the 75 prospects and the 14 linked reviewers whose translation carries no Czech text (one more has headlines but no body, hence 410); the style sample is gender-free by construction, see below |
| `lifecycle_stage`                                              | 500             | every contact: six RFM stages from the order dates, `prospect` for the 75 without an order (204 loyal, 148 active, 44 new, 11 win-back, 9 at risk, 9 churned)                                                                                                                               |
| `reviewer_gender` / `gender_paired`                            | 305 / 236       | the reviewer's inferred gender and whether it matches the contact's; see the section below                                                                                                                                                                                                  |

Company addresses are drawn exactly like contact addresses — one ČSÚ
municipality draw feeding city / postal code / district / region, and the same
street format — so the substrate has one address shape rather than two.

**The style sample is gender-free by construction (D-DB-6, 2026-09-04).**
`style_excerpt` is the longest translated review body, cut to 600 characters,
that contains no Czech first-person form revealing a gender ("koupil jsem",
"jsem používal", "byla", "rád"). The reason is the translator: it writes the
past tense masculine for 377 of 410 reviewers whoever wrote the original, and
UC-01's level L3a hands the sample to the model as "mirror this style", so a
woman would be styled from text that speaks as a man. The filter in
`pipeline/build_substrate_db.py` (`_GENDERED_FIRST_PERSON`) rejects any word
ending in "-l" / "-la" next to "jsem" / "bych". Until 2026-09-04 it demanded a
consonant before the "-l" and so let the everyday forms through: 68 women's
samples carried a masculine form. Of two measured fixes the user chose the one
that keeps every contact: a contact whose every body carries a gendered form
gets the longest body with those sentences cut out instead of no sample, so
the UC-01 reading set is unchanged. Result: 388 whole bodies, 22 stripped
bodies (410 = every contact with a Czech body; before the fix 3 of them had no
sample at all), 0 women with a masculine form; 382 samples reach the
600-character cap (cut at a word boundary, so up to 599 characters) and the
shortest is 172. The style-match metric never reads this column; it reads all
of the contact's reviews.

### The four customer segments

The first 425 contacts are paired with the stratified Amazon reviewers inside
each group, gender-matched wherever the reviewer's gender is known (see "Who is
behind the history" below), and the substrate deliberately holds **more contacts
than reviewers**:

| segment      | n   | linked | orders | Czech text | median products | what it is                           |
| ------------ | --- | ------ | ------ | ---------- | --------------- | ------------------------------------ |
| A            | 300 | 300    | 39 384 | 296        | 113             | heaviest buyers                      |
| B            | 50  | 50     | 3 230  | 40         | 68              | most prolific writers                |
| C            | 75  | 75     | 3 337  | 75         | 44              | thinnest histories the source allows |
| _(prospect)_ | 75  | 0      | **0**  | 0          | —               | nobody has ever sold to them         |

The prospects are the point: every real CRM holds contacts with no purchase
history — leads, event signups, imported lists — and they are the only **true
cold-start** customers available here. The Amazon "5-core" source floors every
reviewer at five reviews, so no _selection_ can produce a customer with none; a
contact with no reviewer can.

Two design rules hold across the segments. The 50 deliberately defective rows
sit inside group C **with** order history, so a downstream failure is
attributable: a contact is either missing a field or missing a history, never
silently both. And the candidate pool is pinned by the frozen translation
(`snapshots/provenance/translation/frozen-reviewers.json`) — selecting outside
it would produce contacts with no Czech text, which is the one thing a Czech CRM
cannot have.

### Who is behind the history: `reviewer_gender` and `gender_paired`

A contact's purchases and writing sample come from a real Amazon reviewer, and
that person has a gender the generated identity did not know about. Until
2026-09-04 the join was positional, a coin flip: of the 293 pairs whose
reviewer gender could be established, 145 (49 %) put a man's history behind a
woman or the reverse. The Czech text hides this rather than showing it — the
translator renders English first-person past tense masculine by default, so
the Czech reviews "speak as a man" for 377 of 410 reviewers whoever wrote them
— which is why the reviewer's gender is taken from the English side.

`build_all` step `reviewer_gender` (`pipeline/build_reviewer_gender.py`) infers
it deterministically from two signals in the cleaned English layer: the raw
dump's `reviewerName` matched against Faker's English given-name lists (unisex
names excluded), and self-reference cues in the review text ("my wife", "as a
mom"). Where both exist they agree in 82 of 86 reviewers; a conflict stays
unknown. Result, committed as `snapshots/amazon/reviewer-gender.json`: 305 of
425 reviewers have a gender (258 men, 47 women — Amazon Electronics is strongly
male), 120 stay unknown.

The generator runner then pairs contacts and reviewers **within each group**
(`substrate/generators/__main__.py::pair_by_gender`): same gender first, unknown
reviewers second, leftovers last. Names, genders, the ČSÚ ratio, the defective
rows' place inside group C and every reviewer's history are untouched; only
who owns which history changed. Measured on the built database:

| contact gender → reviewer gender | male | female | unknown |
| -------------------------------- | ---- | ------ | ------- |
| female (223)                     | 57   | 47     | 119     |
| male (189)                       | 189  | 0      | 0       |

Known mismatches fell from 145 to 57, and no man carries a woman's history.
Two columns record the outcome per contact: `reviewer_gender` ('m' / 'f' /
NULL when unknown or a prospect) and `gender_paired` (1 when the reviewer's
gender is known and equals the contact's; 236 contacts). A use case that needs
a gender-consistent behavioural layer selects `WHERE gender_paired = 1`; the
remaining exposure — 57 women with a man's history plus 119 with an unknown —
is a stated limitation of joining a generated identity to a real behaviour.

### Derived attributes: lifecycle stage, and what the recommender produced

`Contact.lifecycle_stage` is computed at build for every contact from its order
dates against the reference date, with the RFM thresholds of
`substrate/lifecycle.py` (Berry & Linoff ch. 5, Kumar & Reinartz section 6.1;
UC-04's `rfm_lifecycle.py` imports the same function, so the arms and the column
cannot disagree). The vocabulary is the `uc_lifecycle_stages` table, keyed by the
code, seeded from `substrate.constants.LIFECYCLE_STAGES`: seven rows with the
Czech and English label and the rule in words. A prompt joins the label
("dlouhodobě věrný zákazník"); a query reads the code (`WHERE lifecycle_stage =
'churned'`). Decision D-DB-4 (2026-09-04).

`uc_recommendations`, `uc_topics` and `uc_aspects` hold what UC-04 produced for a
contact: the top-K products with a one-sentence Czech reason, the interest
themes clustered from the titles of what they bought, and the product aspects
they praise or criticise. They are **loaded by the database build from UC-04's
committed result file** (`ucs/uc04_matchmaker/results/uc04_to_uc01_handoff.json`),
re-keyed from the Amazon reviewer to the contact that owns that history today,
exactly as the inferred OCEAN profiles are loaded from UC-01's inference file.
So UC-04 runs first when its results are to be regenerated, `build_all --from
database` reloads the tables, and UC-01 reads only the database; a fresh clone
gets the tables from the committed file without running UC-04 at all. Empty
means "UC-04 has not produced this", never a fabricated row: 539
recommendations and 540 topics for 108 contacts today, 0 aspects. Decision of
2026-09-04 (UC-04 → DB).

`Product.name_cs` is the Czech product title the frozen translation run
produced (16 067 of 18 213 products, cleaned of hidden characters; NULL where
the translator never saw the title). The catalogue stays English otherwise —
descriptions were never translated. A prompt that wants Czech uses `name_cs`
and falls back to `name`; the database never invents a title. Decision D-DB-5
(2026-09-04).

Sex and age come from one joint draw over the ČSÚ age x sex table
(`csu_sampler.sample_age_sex`), so the cohort carries the real population ratio
rather than a coin flip: 262 f / 225 m, a 53.8 % female share against the 51.3 %
of the Czech 18–90 population. `district` and `region` are the LAU1 / NUTS3 units
of the drawn municipality.

`ocean` is SQL NULL when absent (the column is declared
`JSON(none_as_null=True)`; without that SQLAlchemy stores the JSON text `'null'`
and `WHERE ocean IS NOT NULL` matches every row). `ocean_source` has no code
reader — it exists so the thesis can state each profile's provenance.

Known gap: `iban` and `bank_account` are drawn independently, so where a contact
has both they describe different accounts. Linking them is part of the UC-02 step
(decision D-DB-2).

## Cross-UC reuse

1. **UC-01 (personalisation)** reads only the database (`ucs/uc01_personalization/data.py`):
   the contact with its prompt digests, the newest purchases joined to the catalogue, the
   lifecycle label, and UC-04's recommendations / topics / aspects from their tables. It
   writes nothing to it; picks and runs are files under its own `snapshots/`.
2. **UC-02 (PII pseudonymisation)** reads its own corpus files under
   `ucs/uc02_pseudonymization/snapshots/`. Under D-DB-2 that corpus is
   regenerated from real `Contact` rows, so the coupling is at build time.
3. **UC-03 (MCP privacy)** is the database's main consumer: `search_contacts`,
   `get_contact` and `search_notes` query it through plain `sqlite3`, and
   `create_note` inserts. Note categories are shared with
   `generators/notes/`.
4. **UC-04 (retail matchmaker)** reads `Contact`, `Review` and `Product` read-only
   through `ucs/uc04_matchmaker/data.py` (D-UC04-A, 2026-09-06: measured identical
   to the snapshots, plus Czech titles and prospects). The outputs for UC-01
   (`ucs/uc04_matchmaker/outputs_for_uc01/`, since 2026-09-07) read the same tables and
   write back only through the handoff file this build loads; nothing in UC-04 parses the
   Amazon JSON any more.

## Not in the database, on purpose

| What                                                   | Where it lives instead                                        |
| ------------------------------------------------------ | ------------------------------------------------------------- |
| Generated messages, error rows, evaluation records     | UC-01 run outputs as JSON + CSV (persistence rule 2026-05-28) |
| Judge calibration fixtures                             | `ucs/uc01_personalization/eval/judge_testset.py` output       |
| UC-02's PII answer key (planted messages + gold spans) | `ucs/uc02_pseudonymization/snapshots/`                        |

Each of these was once a table (`uc_generated_messages`, `uc_error_results`,
`uc_evaluation_records`, `uc_judge_test_messages`, `uc_pii_corpus_messages`,
`uc_pii_spans`); none ever had a reader and the first four never held a row.
`tests/substrate/schema/test_schema.py::test_experiment_bookkeeping_is_not_persisted`
guards the decision so a re-add has to be deliberate.

## Schema-evolution rules

- **Forward-compatible additions** (new optional fields, new entities) — proceed;
  coordinate across UCs that share the entity. A new table needs an answer to
  "is this CRM content or experiment bookkeeping?"
- **Breaking changes** (rename / type narrowing / required-field additions) —
  update all UCs that touch the entity and run the relevant tests.
- **Migrations**: no Alembic. Rebuild from the committed JSON snapshots with
  `python -m substrate.pipeline.build_substrate_db --force` after any change.
- **Virtual tables**: `SQLModel.metadata.create_all` cannot declare an FTS5
  index, so the assembler creates and fills `uc_reviews_fts` itself after the
  rows are in. A test database built through `create_all` alone has no index;
  readers that need it must build against the assembled database.
- **Gitignored data**: `substrate/snapshots/substrate.db` is gitignored;
  regenerate from the snapshots and `substrate/generators/` deterministically
  (seed 42). The schema (`models.py`), snapshots and generators are versioned.
