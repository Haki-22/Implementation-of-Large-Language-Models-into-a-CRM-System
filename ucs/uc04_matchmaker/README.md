# UC-04: Customer x product matchmaker (classical ML versus language models)

A recommendation arena on the shared CRM substrate. For every linked customer the
chronologically last purchase is hidden; every recommender ("arm") gets the rest of
the history and the shop catalogue and has to place the hidden product high. The
question of the use case is whether a language model _replaces_ or _complements_
classical machine learning on this task; the arena answers it by measurement, all
arms on the same customers, the same catalogue and the same protocol.

## What it reads and how it scores

- **Data**: `substrate.db` only (`data.py`): `uc_contacts` (the 425 contacts that own
  an Amazon reviewer; the 75 prospects have no purchases and fall out of
  leave-one-out by construction), `uc_reviews` (one review = one purchase; rating,
  date, English and Czech text), `uc_products` (18 213 products; English title,
  category, description, price; Czech title for 16 067).
- **Leave-one-out**: the last review by date is hidden; 88 customers have several
  reviews on their final day, the tie is broken by the lowest review id.
- **Language branches**: `en` and `cs` keep the same customers, histories and hidden
  items and differ only in the text an arm reads: review text and headline in Czech
  (empty for the 3 207 reviews without a usable Czech translation) and the Czech product
  title where it exists (16 067 of 18 213; descriptions stay English). Arms that read
  no text score identically in both branches, the data-integrity check; arms that read
  text pay the Czech tax.
- **Two protocols, both always reported** (`protocols.py`):
    - `full`: the hidden product ranked against the whole catalogue; guessing scores
      10 / 18 213 = 0.05 % at top 10. What a shop would see; on this sparse catalogue
      and these heavy buyers every arm scores single digits of 425, so the protocol
      says "above the random floor or not", never a ranking of arms.
    - `sampled`: the hidden product ranked against 100 products the customer never
      bought, drawn once per customer with a fixed seed and identical for every arm;
      guessing scores 10 / 101 = 9.9 %. The protocol of the recommender literature
      and of language-model rankers; an easier task, not comparable with `full`
      (Krichene & Rendle 2020), which the card says next to every number.
- **Two data regimes, never in one table** (`population.py`): `crm` = an arm learns
  only from the shop's own customers; `population` = the collaborative arms learn
  from every reviewer in the public Amazon Electronics 5-core dump (192 403 people,
  1.69 M reviews, streamed from the md5-pinned raw file the substrate already
  downloads) and are then applied to the shop's customers.
- **Ties**: an arm without an opinion on a product (`-inf`) leaves it tied at the
  bottom; ties are broken by a seeded shuffle, so no arm borrows popularity or
  catalogue order. A customer's own purchases are excluded from the ranking.

## The arms (`arms/`)

Every arm is one module with the same interface: `score(arena, *, population=None)`
returns a `float32` matrix customers x products over the whole catalogue; the
harness masks, ranks and scores. `ARMS` in `arms/__init__.py` is the registry.

| arm | what it is | learns from | population regime |
| --- | --- | --- | --- |
| `popularity` | most-bought products, the same list for everyone | who bought what | yes |
| `als_cf` | ALS collaborative filtering (implicit feedback, 64 factors) | who bought what | yes |
| `svd_mf` | SVD matrix factorisation of the rating matrix (50 factors) | who bought what | yes |
| `apriori_rules` | Apriori association rules, "who bought X bought Y" | who bought what | no |
| `adamic_adar` | Adamic-Adar link prediction on the customer-product graph | who bought what | no |
| `naive_bayes` | multinomial naive Bayes, bought products as features | who bought what | no |
| `bm25_text` | BM25: the customer's review words against product texts | review + product text | no |
| `dense_e5` | multilingual-e5 vectors; the customer is the mean of the products bought | product text | no |
| `bert_encoder` | DistilBERT (en) / Czert-B (cs) [CLS] vectors, no fine-tuning | product text | no |
| `hybrid_als_dense` | equal-weight sum of scaled ALS and dense scores | both | no |
| `lightgbm_features` | boosted trees on category, price, length and overlap features | engineered features | no |
| `svm_features` | linear SVM on the same features | engineered features | no |

`--arms fast` runs everything but the three encoder arms (`dense_e5`, `bert_encoder`,
`hybrid_als_dense`), which took 7 to 25 minutes of CPU in the recorded environment to encode the catalogue once;
their vectors are cached under `eval/cache/` (gitignored, regenerable).

The language-model methods live in their own registry, `arms/model/` (below); they
run on the fixed sample, not on all 425, and never in `run`.

**The model-arm sample** (`sample.py`, `eval/samples/model-arms-100.json`): a model
arm costs one call per customer and branch, so it runs on a fixed stratified sample
of 100 customers (60 A / 20 B / 20 C) instead of all 425, the same list for every
model arm and for the OCEAN inference that feeds the profile re-ranker
(`ucs/uc01_personalization/ocean_inference.py`). Rule: per group, the linked contacts of
UC-01's pick first (so the model explains recommendations and infers a personality for
the people whose messages UC-01's reading pass looks at), then a seeded draw without
replacement from the arena's remaining customers of that group. The file records the
rule, the seed, the ids per group and per customer the facts a table may split on;
every run that uses it copies it into its own folder.

## How to use

Complete the [root setup](../../README.md#quickstart). Run commands from the repository root; inventory paths in this document are relative to UC-04. Replace placeholders before running. These are separate workflows, not one installation script. Population runs require the optional raw Amazon dump; encoder runs can download model weights on first use.

```bash
# From the repository root with the virtualenv active (pip install -e .).
python -m ucs.uc04_matchmaker status                      # database, branches, dump, caches; no computation
python -m ucs.uc04_matchmaker run --arms fast             # both branches, both protocols, in-CRM regime
python -m ucs.uc04_matchmaker run --arms fast --regimes crm,population
python -m ucs.uc04_matchmaker run --arms dense_e5,hybrid_als_dense --langs en,cs
python -m ucs.uc04_matchmaker report --run ucs/uc04_matchmaker/eval/runs/<folder>   # re-render TABLE.md + RESULTS.md
python -m ucs.uc04_matchmaker facts --population          # the data facts behind the numbers, into a run folder
python -m ucs.uc04_matchmaker run --arms als_cf           # one arm into its own folder; the appendix files are untouched
python -m ucs.uc04_matchmaker attachment --run ucs/uc04_matchmaker/eval/runs/<folder>   # appendix files from a chosen folder (a full run does it itself)
python -m ucs.uc04_matchmaker sample                      # the fixed customer sample of the model arms -> eval/samples/model-arms-100.json
python -m ucs.uc04_matchmaker personality                 # the paired personality-feature comparison -> run folder + attachments/uc04-personality-feature.{csv,md}
python -m ucs.uc04_matchmaker model-run --provider mock --limit 3   # the model methods, plumbing only (see below)
python -m ucs.uc04_matchmaker model-run --methods rank_candidates,describe_and_retrieve --provider codex --model gpt-5.6-terra --tier low --force-llm --role comparison   # the same methods on a second provider; never the record
python -m ucs.uc04_matchmaker card                        # the one-page card eval/RESULTS.md from the runs of record of every kind
```

Every kind of run is its own command with a plain-Python function behind it
(`arena.run`, `facts.run`, `attachment.build`), so the frontend can call the same
functions through the bridge without a second implementation.

`run` executes classical/local-model arms without hosted language-model calls;
`model-run --force-llm` does make live calls. `mock` checks plumbing only.
`report`, `attachment` and `card` rebuild saved tables without inference but overwrite
their target reports. Full runs can also update shared attachment files. Use a
separate copy when preserving the supplied evidence.

A classical `run` writes a new folder under
`eval/runs/` (named date · what · on what · how many customers) with `config.json`
(database hash, customer and catalogue counts, population identity, package
versions, seed), `scores/<regime>-<arm>-<lang>.json` (numbers, per-customer rank of
the hidden item, top-10 lists), `TABLE.md` (generated comparison tables) and
`RESULTS.md` (the one-page card). A run folder is the provenance of a number and
keeps the measurement inputs and scores. `facts` writes `facts.json` and its reports
in a separate folder, not the arena score layout. `eval/runs/README.md` lists the saved folders.

Thread caps for the encoders and matrix factorisations: `OMP_NUM_THREADS=4 nice -n 19`.

## Run of record

`eval/runs/2026-09-07-arena-crm-population-12-arms-en-cs-425-customers/` — all twelve
arms, both branches, both protocols, both regimes, on the database as rebuilt after the OCEAN
inference and the outputs for UC-01 (the same database the model methods ran on); 5 min 51 s
with cached encoder vectors, no model calls. Data facts: `eval/runs/2026-09-07-data-facts-425-customers-population/`.
The first full run of 2026-09-06 stays as the provenance of the lab-log entries of that day; the
rerun reproduced 56 of its 60 cells, the four LightGBM cells moved (full 2 → 3, sampled 150 → 145).
Hits at top 10 of 425 customers, English / Czech branch (guessing: 0.2 under `full`, 42
under `sampled`); arms that read no text score identically in both branches by construction:

| arm | full, CRM | sampled, CRM | sampled, population |
| --- | --- | --- | --- |
| `popularity` | 1 / 1 | 125 / 125 | 50 |
| `als_cf` | 6 / 6 | 119 / 119 | 182 |
| `svd_mf` | 6 / 6 | 125 / 125 | 157 |
| `apriori_rules` | 5 / 5 | 110 / 110 | — |
| `adamic_adar` | 3 / 3 | 154 / 154 | — |
| `naive_bayes` | 4 / 4 | 91 / 91 | — |
| `bm25_text` | 1 / 2 | 57 / 75 | — |
| `dense_e5` | 4 / 2 | 131 / 110 | — |
| `bert_encoder` | 1 / 1 | 94 / 46 | — |
| `hybrid_als_dense` | 8 / 7 | 148 / 128 | — |
| `lightgbm_features` | 3 / 3 | 145 / 145 | — |
| `svm_features` | 1 / 1 | 65 / 65 | — |

Reading: against the whole catalogue every arm sits within 1 to 8 hits and inside one
another's confidence intervals (reruns reproduce every cell except LightGBM's, which move by one to five hits), so the full protocol says only "above the random floor";
against 100 sampled negatives the arms separate, learning from the public population lifts
ALS from 119 to 182, and the population's most-bought products barely beat guessing for
these customers (50). The Czech tax is visible wherever an arm reads text: dense 131 → 110,
the hybrid 148 → 128, the BERT pair 94 → 46; BM25 goes the other way (57 → 75) within
overlapping intervals. The facts run explains the floor: density 0.588 %, the median product
has one buyer, 108 of the 425 hidden items were bought by nobody else, and the same
population ALS scores 2.5 % on 2 000 ordinary reviewers against 0.7 % on these heavy buyers.

## The model methods (`arms/model/`, `model_arena.py`)

The question of the use case, whether a language model _replaces_ or _complements_
classical recommending, is answered by five methods that call a model, scored by the
same protocol code as the classical arms on the same customers, candidate lists and
seeds, and paired per customer against ALS (and popularity) on exactly those lists.
The method registry and versioned prompts below define the implemented comparison.

| method | what the model gets | ML input | protocol | customers |
| --- | --- | --- | --- | --- |
| `rank_candidates` | whole history + the 101 sampled candidates in a seeded random order; returns the full permutation | none | sampled | the sample of 100 |
| `describe_and_retrieve` | whole history; writes three listing lines for the next purchase; multilingual-e5 `query:` vectors against the `dense_e5` catalogue cache, score = best cosine | the dense index | full and sampled | the sample of 100 |
| `rerank_als` | the 101 candidates in ALS order with scores; may move one only where the history supports it | ALS order + scores | sampled | the sample of 100 |
| `rerank_als_with_profile` | `rerank_als` plus the profile the CRM holds: Big Five estimate, lifecycle stage, interest topics, persona and aspects where present; ties only | ALS + the profile | sampled | the sample of 100 |
| `rerank_als_top200` | the 200 best ALS candidates of the whole catalogue in ALS order, for the customers whose hidden item is among them (44 at the current database) | ALS top 200 | full | the reachable ones |

Common to all: the whole purchase history in the prompt (median 91 titles in the
sample, at most 407, up to ~45 k characters with 200 candidates); candidates as
`C001` … (the model never sees an ASIN); one prompt catalogue, `arms/model/_prompts.py`,
with an English and a Czech text under one `PROMPT_VERSION` (the Czech branch is Czech in
the instruction and the data, so the branch difference is the Czech tax on both at once);
a JSON schema the provider enforces; a strict parser (an unknown or repeated id fails the
call, ids left out are appended in prompt order and the call is `partial`); every call
stored in `calls/<method>-<lang>-<provider>/<contact_id>.json` with the provider-returned
payload and parsed answer, status, seconds, resolved model, tier, CLI version, prompt version and database
hash; `--reuse <run>` takes over identical calls from an earlier folder. A method returns
`k − position` for the candidates it ordered and `-inf` elsewhere (cosine over the whole
catalogue for `describe_and_retrieve`), and `protocols.py` scores it unchanged. The
references `als_cf` and `popularity` are scored on the same subsets
(`scores/reference-<arm>-<subset>.json`); `pairs.json` holds the per-customer paired
differences with the two-sided sign test (method 1 and 2 against ALS and popularity, 3
against ALS, 4 against ALS and against 3, 5 against ALS on the reachable customers).

```bash
python -m ucs.uc04_matchmaker model-run --provider mock --limit 3                     # plumbing only; not a measured model result
python -m ucs.uc04_matchmaker model-run --methods rank_candidates --limit 5 --provider agy --model gemini-3.8-flash --tier medium --force-llm   # smoke, live calls
python -m ucs.uc04_matchmaker model-run --methods all --provider agy --model gemini-3.8-flash --tier medium --force-llm   # the run of record: 4 x 200 + 2 x 44 calls
python -m ucs.uc04_matchmaker model-run --methods all --provider codex --reuse ucs/uc04_matchmaker/eval/runs/<folder> --force-llm --role comparison            # a second provider on identical inputs
python -m ucs.uc04_matchmaker model-report --run ucs/uc04_matchmaker/eval/runs/<folder>                    # re-render TABLE.md + RESULTS.md
```

A run writes `eval/runs/<date>-model-methods-<n>-methods-<provider>-<model>-<tier>-<langs>-<n>-customers/`
with `config.json` (methods, the full prompt texts and schemas, the sample and its rule,
which profile fields each customer had, the reachable customers, provider, database and
package identity), `sample.json`, `calls/`, `scores/`, `pairs.json`, `TABLE.md` and
`RESULTS.md`. The methods may run one provider at a time (2026-09-07: methods 1 and 2
on agy gemini-3.8-flash medium, 3–5 on Codex gpt-5.5 low, the pair 3 × 4 inside one
folder), so the appendix is built from **one record folder per method**: the newest
folder that holds the method on the whole sample with a real provider
(`attachment.record_model_runs`). Once every method has one, a run rewrites
`attachments/uc04-model-methods.{csv,md}` (results with the provider per row,
paired differences, the model's lines beside the real next purchase) and `uc04-arms.md`,
the single table of every method of the arena generated from the two registries (the arms
are described once in the whole thesis, in that table); `attachment --model-run a,b` does
it by hand. A smoke (`--limit`) keeps its own tables; a mock run touches neither the
appendix nor the runs README and is not part of the submitted evidence. Real providers fail closed unless `THESIS_LLM_CALLS` is enabled;
`--force-llm` enables it for the command. A call that the provider refused (quota, usage window, network) is
a failed row; `--reuse <folder>` re-sends only those, so a method's record is the last
folder of its reuse chain (the copied calls name the folder they came from).

### Run of record of the model methods (2026-09-07)

One record folder per method under `eval/runs/` (each the last link of its `--reuse`
chain; the folder's `RESULTS.md` is the card, `attachments/uc04-model-methods.{csv,md}`
the appendix). Hits of the hidden purchase at top 10; the references are ALS and popularity
scored on exactly the same customers and candidate lists:

| method | provider / model / tier | protocol | customers | en | cs | reference ALS | popularity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rank_candidates` | agy / gemini-3.8-flash / medium | sampled | 100 | 64 | 64 | 28 | 34 |
| `describe_and_retrieve` | agy / gemini-3.8-flash / medium | sampled | 100 | 25 | 21 | 28 | 34 |
| `describe_and_retrieve` | agy / gemini-3.8-flash / medium | full | 100 | 2 | 3 | 3 | 0 |
| `rerank_als` | codex / gpt-5.5 / low | sampled | 100 | 57 | 54 | 28 | 34 |
| `rerank_als_with_profile` | codex / gpt-5.5 / low | sampled | 100 | 51 | 48 | 28 | 34 |
| `rerank_als_top200` | codex / gpt-5.5 / low | full | 44 | 11 | 10 | 6 | — |

Paired per customer (sign test): the model alone and the ALS re-rank beat ALS in both branches
(p < 0.001); the profile lowers the re-rank by 6 hits in both branches (p 0.15 / 0.11); the
top-200 re-rank adds 5 / 4 hits over ALS on the 44 (p 0.13 / 0.29); describe-and-retrieve
separates from nothing. Calls: agy medium returned the full permutation in 94 % / 90 % of the
calls; Codex low left 1–2 ids out in half of them and repeated an id in ~4 % (a failed call; 3
of 488 stayed failed after two `--reuse` links and passed on the fourth). Provider failures were retained as failed rows and retried through the recorded reuse
chains. The paired methods 3 and 4 share a provider. Every final record folder has
0 failed calls; some earlier reuse folders were removed after consolidation. The run inventory
and retained configs/call metadata identify the surviving evidence; a
`reused_from` path is not proof that its original folder is still shipped.

### The same method on a second provider (`--role comparison`)

A run launched with `model-run --role comparison` runs the same methods on the whole sample with
another provider or model. Its folder carries `"role": "comparison"` in `config.json`, is kept
beside the record and **never replaces it**: `model_arena.is_record_run` excludes it, the appendix
is built from record folders only, and the card lists every comparison folder next to the record
of the same method (block 6, `attachment.comparison_model_runs`). Comparisons of 2026-09-07
(sampled protocol, hits at top 10 en / cs of 100; ALS 28 on the same lists):

| method | record | second provider |
| --- | --- | --- |
| `rerank_als` | codex gpt-5.5 low 57 / 54 | agy gemini-3.8-flash medium **58 / 56** |
| `rank_candidates` | agy gemini-3.8-flash medium 64 / 64 | codex gpt-5.6-terra low **46 / 45** (ids dropped in 106 of 200 calls, never the hidden item) |
| `describe_and_retrieve` (sampled) | agy 25 / 21 | terra 29 / 27 |
| `describe_and_retrieve` (full catalogue) | agy 2 / 3 | terra 0 / 0 |

Reading: the hybrid scored similarly in these two tested configurations; the model-alone
ranker did not. Describe-and-retrieve remained weak. In the recorded smokes,
gpt-5.6-luna often failed to return a valid 101-id permutation (24 of 26 calls at low repeat an id, 5 of 10
at medium; terra low 0 of 10): the aborted folder and the two smokes stay as the evidence. A branch
whose every call failed prints `NO RESULT` in front of its hits (the score is then a random order).

## The personality feature (`personality.py`)

UC-04 compares a personality profile inferred from review text with a randomly
sampled profile. Neither is a measured personality assessment. Since 2026-09-06 every linked customer carries a Big Five
profile a model inferred from their English reviews (`ocean_source = 'inferred'`), and 271
also carry the generator's sampled profile, so the comparison is measurable:
`python -m ucs.uc04_matchmaker personality` runs the two feature arms (LightGBM, linear
SVM) in three variants on the same customers, candidate lists and seeds, `none` (the
recorded arms), `inferred` and `sampled` (five extra customer columns; a customer without
the profile gets NaN for LightGBM and the scale midpoint for the SVM), and pairs them per
customer: hits in the top 10, discordant pairs, the two-sided sign test. Pairs that involve
the sampled profile are counted on the customers who have both. The run folder
(`eval/runs/<date>-personality-feature-…/`) holds the scores per arm × variant × branch,
`pairs.json`, `TABLE.md` and the card, and rewrites
`attachments/uc04-personality-feature.{csv,md}`. LightGBM moves by a few hits
between runs even with pinned threads, so differences of that size need cautious interpretation.

## The one-page card (`eval/RESULTS.md`, `card.py`)

The page a reader takes as the result of the use case, in the shape of UC-02's
`eval/RESULTS.md`: the data behind the numbers, the classical arena, the personality
column, the outputs for UC-01 and the model methods, every block naming the run folder its
numbers come from. `python -m ucs.uc04_matchmaker card` assembles it from the newest run
of record of every kind (`attachment.run_folders`, `record_model_runs`) and rewrites it;
run it again after any new record run (a `--reuse` link that completes a method, a rerun
of the arena on a rebuilt database). Nothing on the page is typed by hand.

## Attachments for the thesis (`attachments/`)

A run saves its numbers into its dated run folder and generates its own readable
`TABLE.md` and `RESULTS.md` from them. The appendix files, `uc04-arena-results.csv`
and `.md` (one row per regime × protocol × arm × branch, Czech table captions) and
`uc04-data-facts.csv` and `.md`, are generated from **one** run folder, the run of
record: a run that covers every registered arm rewrites them from its own folder
when it finishes, every `facts` run rewrites the facts pair, and a partial run such
as `run --arms als_cf` keeps its own tables and leaves the appendix alone. Reruns are not fully deterministic: a second full run reproduced 56 of 60 cells
exactly and the four LightGBM cells moved by one to five hits; that arm is not bit-reproducible in this environment even with
pinned threads and stays inside its interval, so a table stitched from several folders
would only lose the provenance of which code and which database it describes. `attachment --run <folder>` writes the same files by hand for a
chosen folder and reproduces their contents apart from generation dates. The other pairs follow the same
rule from their own runs: `uc04-personality-feature.{csv,md}` (every `personality` run),
`uc04-outputs-for-uc01.{csv,md}` (a `for-uc01 run` over the whole pick; a smoke keeps
its card only) and `uc04-model-methods.{csv,md}` (one record folder per model method,
the newest complete one, because the methods run per provider); `uc04-arms.md` is
generated from the two registries by every `attachment` build. The appendix of the thesis quotes these files the way Příloha A quotes
`attachments/tokenizer-fertility.csv`; the tables are wide, so the appendix page is
rendered landscape.

## The outputs for UC-01 (`outputs_for_uc01/`)

The top levels of UC-01's personalisation ladder need, per contact, what a classical
recommender cannot produce (the assignment's category C): recommended products **with
a Czech sentence saying why**, a **persona** (two Czech sentences about the buying
behaviour) and the **product aspects the customer praises or criticises** (from the
Czech reviews, each with a verbatim quote); plus two classical fields, **interest
topics** (LDA over the catalogue titles, Czech where the catalogue has them) and the
**lifecycle stage** (the substrate's rule). Who gets what is a rule: the model-written
prose for the linked contacts of UC-01's pick, the classical fields for every linked
contact; the recommendations are ALS collaborative filtering over the whole purchase
history (nothing hidden, the recommendation-use view). Every call is recorded with its verbatim
prompt; a reason must cite purchase ids that exist in the history it was shown, an
aspect quote must be verbatim in the reviews, and the card reports how many were.

```bash
python -m ucs.uc04_matchmaker for-uc01 run --provider mock --limit 2 --top-k 3        # plumbing, no spend
python -m ucs.uc04_matchmaker for-uc01 run --provider agy --model gemini-3.8-flash --tier medium --force-llm   # live calls
python -m ucs.uc04_matchmaker for-uc01 freeze --run ucs/uc04_matchmaker/eval/runs/<folder>      # -> results/uc04_to_uc01_handoff.json
python -m substrate.pipeline.build_all --force --from database                        # loads it into uc_recommendations / uc_topics / uc_aspects
```

Modules: `prompts.py` (the three Czech prompts, versioned), `calls.py` (one recorded
call), `inputs.py` (histories with ids, Czech reviews, categories, lifecycle labels),
`reasons.py`, `persona.py`, `aspects.py`, `topics.py`, `handoff.py` (the file in the shape
the database build reads; `freeze`), `run.py` (the run folder, the card, the appendix pair
`attachments/uc04-outputs-for-uc01.{csv,md}`). The May chain that produced the
June handoff (`llm_outputs/`, `handoff/`, `supporting/`, `eval_loo.py`) was replaced on
2026-09-07 and its inputs removed with it; the run folder of record is the provenance.
Run of record: `eval/runs/2026-09-07-outputs-for-uc01-codex-gpt-5.6-luna-low-16-contacts/`
(Codex gpt-5.6-luna low, 112 calls for the pick `uc01-personalization-20-level`: 80 of 80 reasons
grounded, 16 personas, 74 of 75 aspect quotes verbatim). The earlier record for the previous pick
(`…-codex-gpt-5.5-low-16-contacts/`, 80 of 80, 78 of 79) and the four smoke folders next to it (agy
gemini-3.8-flash, Claude Haiku, Claude Sonnet, Codex; 2 contacts each) stay as the record of the
provider choice.

## Tests

```bash
pytest tests/ucs/uc04_matchmaker          # database reader, both protocols, arm interface, run folder, model methods with the mock (toy substrate)
pytest tests/test_documented_entry_points.py -k uc04
```

## External dependencies

`implicit` (ALS), `scipy` (SVD), `mlxtend` (Apriori), `scikit-learn` (naive Bayes,
SVM), `lightgbm`, `rank_bm25`, `simplemma` (Czech lemmatisation for BM25),
`sentence-transformers` + `transformers` + `torch` (the encoder arms). The population
regime needs the raw dump `substrate/pipeline/data_acquisition/downloaded/reviews_Electronics_5.json.gz`
(not shipped; `python -m substrate.pipeline.data_acquisition.fetch_and_filter --download`
re-fetches it from SNAP and verifies the md5).

## Files

```
ucs/uc04_matchmaker/
├── __main__.py            status | run | report | facts | attachment | sample | personality | for-uc01 run/freeze | model-run | model-report | card
├── arena.py               the runner: arms x branches x regimes x protocols -> run folder
├── data.py                Arena / Customer / Interaction from substrate.db (leave-one-out, branches)
├── protocols.py           full and sampled protocols, hits@K, NDCG@10, MRR@10, Wilson intervals, reach@K
├── population.py          the public dump as a training matrix for the population regime
├── facts.py               the data facts behind the numbers, into a run folder (facts command)
├── attachment.py          attachments/uc04-*.{csv,md} from one run folder (attachment command)
├── sample.py              the fixed customer sample of the model arms and the OCEAN inference (sample command)
├── personality.py         the paired personality-feature comparison of the feature arms (personality command)
├── arms/                  one module per classical recommender + _common.py, _features.py
├── arms/model/            the five model methods + _prompts.py (the versioned prompt catalogue, en + cs) + _calls.py (recorded call, parser, score matrix)
├── model_arena.py         the run of the model methods: sample x branches x methods with one provider -> run folder, pairs, card (model-run command)
├── card.py                the one-page card eval/RESULTS.md from the runs of record of every kind (card command)
├── eval/RESULTS.md        the one-page card (generated) · eval/runs/ run folders (committed) · eval/samples/ the model-arm sample (committed) · eval/cache/ encoder vectors (gitignored)
├── outputs_for_uc01/      what UC-04 hands to UC-01: reasons, persona, aspects (model), topics + lifecycle (classical); run, freeze
├── future-work.md         what the arena does not do and would be the next step
└── results/               uc04_to_uc01_handoff.json, the handoff of record the database build loads (`for-uc01 freeze`)
```
