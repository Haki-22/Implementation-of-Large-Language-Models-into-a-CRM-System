# Substrate — shared synthetic CRM dataset

Everything needed to rebuild the dataset every use case reads from.
The substrate is a fictional Czech e-commerce retailer with 500
customer/B2B contacts, 8 partner companies, 18 213 products, 45 951 orders and
the 45 951 reviews behind them (English original + Czech translation, full-text
indexed), 80 Czech CRM notes and 26 outreach briefs. CRM identities are synthetic. Public
Amazon reviews supply behaviour and text; their contents are not guaranteed to
be free of incidental personal information.

An `__init__.py` in every folder makes it a package; the ones that do more than mark a package (the contact recipe, the schema re-exports) are named in their folder's README.

## Structure

```
substrate/
├── data/          Committed inputs: the two reduced ČSÚ tables + the vendored stop-list (provenance headers).
├── schema/        SQLModel entities, async session helpers, DB docs.
├── generators/    Seeded synthetic-data generators (no LLM, no network).
├── pipeline/      Build scripts that assemble the substrate from raw data.
├── snapshots/     Versioned data artifacts and the gitignored SQLite DB.
```

## How to use

Complete the [root setup](../README.md#quickstart) first. Commands below use the repository root; paths in the inventory are relative to `substrate/`. Rebuilding the database replaces local CRM changes, including notes added through UC-03.

### Reading from the substrate

UC code never regenerates the substrate. UC-01 (the single-call generation, the picker, the
metrics), UC-03's tools, the frontend bridge and UC-01's OCEAN inference read `substrate.db`.
UC-02 scores its saved corpus without this database; its corpus builder and
review false-alarm evaluation read CRM rows. To read contacts through the async
SQLAlchemy session, run:

```python
import asyncio

from substrate.schema.session import get_session
from substrate.schema.models import Contact
from sqlmodel import select

async def main():
    async with get_session() as session:
        result = await session.execute(select(Contact))
        contacts = result.scalars().all()
        print(f"Loaded {len(contacts)} contacts")

asyncio.run(main())
```

### Rebuild from scratch

One command runs the whole chain in order, stops at the first failure, ends with
the text-hygiene audit gate and prints a manifest (table row counts + snapshot
md5s):

```bash
python -m substrate.pipeline.build_all --verify   # unpack the shipped snapshots, then check every input; without the raw dumps it stops at step 1 with exit 1
python -m substrate.pipeline.build_all --force    # full rebuild
python -m substrate.pipeline.build_all --force --from database   # just re-assemble the DB
```

The steps it runs, in order:

| # | step | what it does |
| --- | --- | --- |
| 1 | `amazon` | Verify the raw Amazon dumps against the pinned size + md5, then stratify 425 reviewers (A=300, B=50, C=75) from the frozen-translation pool; contacts 426–500 are prospects with no reviewer |
| 2 | `csu` | Verify / rebuild the reduced ČSÚ tables (age x sex, all 6 254 municipalities) + the Czech Post postal codes |
| 3 | `english` | Clean the original Amazon text and rebuild the translation queue; `--check-against-frozen` proves the queue contains only item ids covered by the frozen translation |
| — | _translation_ | **FROZEN, never re-run.** Ran once 2026-05-29; result in `snapshots/provenance/translation/`. Facts: `pipeline/translation_pipeline/README.md` |
| 4 | `clean` | Join the frozen Czech text with the English layer and the product catalogue |
| 5 | `reviewer_gender` | Estimate each reviewer's gender with local heuristics from their Amazon name + self-references in the English reviews (`snapshots/amazon/reviewer-gender.json`; 305 of 425 known) |
| 6 | `contacts` | Generate the 500 Czech identities, pair them with the reviewers by gender inside each group, then the 80 Czech CRM notes and the 8 partner companies |
| 7 | `ocean` | Re-derive the OCEAN projection report from the contacts snapshot |
| 8 | `database` | Assemble `substrate.db` from the committed snapshots |
| — | audit gate | No hidden-character class may survive in any output (`utils.text_hygiene`) |

A full rebuild fetches any missing raw input by itself (the two Amazon dumps,
~680 MB, and the ČSÚ + Czech Post files, ~885 MB; every file md5-pinned, see
`pipeline/data_acquisition/inputs.py`), so on a fresh clone `build_all --force`
is the whole "start here". `--verify` never downloads. The fetchers stay
runnable on their own:

```bash
python -m substrate.pipeline.data_acquisition.fetch_and_filter --download
python -m substrate.pipeline.data_acquisition.fetch_csu --download
```

Every step is also runnable on its own; see each module's `--help`.

For day-to-day work the committed JSON snapshots in `snapshots/` are enough and
only the database step has to run: `build_all --force --from database` (~15 s for the step, ~45 s with the audit gate and manifest).

## Outputs

- `snapshots/substrate.db` — the SQLite database of **CRM content**: `uc_contacts`,
  `uc_notes` (with `author` and the audit sequence of the writing call), `uc_change_log`
  (field changes requested through UC-03's server), `uc_companies`, `uc_products`, `uc_orders`, `uc_reviews` (+ the FTS5
  index `uc_reviews_fts`), `uc_message_briefs`, plus the derived customer attributes
  `uc_lifecycle_stages`, `uc_recommendations`, `uc_topics`, `uc_aspects` (the last
  three loaded from UC-04's committed result file) — gitignored, 347 MB, regenerable
  in ~15 s. Experiment output and UC-02's PII answer key are deliberately files, not
  tables — see `schema/DB.md`.
- `snapshots/contacts/`, `snapshots/amazon/`, `snapshots/briefs/` — versioned JSON snapshots from which `substrate.db` is assembled.
- `snapshots/ocean/` — the generator's OCEAN projection (pre-inference state: 326 of 500 with a profile). Evidence, not an input: no code reads it.
- UC-02's corpus is generated from the contact and company rows into `ucs/uc02_pseudonymization/snapshots/`; nothing PII-corpus-shaped lives under `substrate/` any more.
- `snapshots/intermediate/` — regenerable working layer (cleaned English snapshot + translation queue); not tracked in git.
- `snapshots/provenance/` — frozen evidence: the one-time translation result, the translator bake-off, the pre-cleaning snapshots, the OCEAN backfill inputs. Never regenerated.

## Determinism

Reproducibility rests on committed snapshots, not on re-running
generators. The synthetic layers (`generators/`) are seeded (`seed=42`)
and designed for repeatable regeneration with the same inputs and dependencies; the raw Amazon layer and the ČSÚ / Czech Post
downloads are pinned by md5 (`fetch_and_filter --verify-only`, `fetch_csu --verify-only`); the stratification is deterministic
(sorted keys); the translation ran once and is frozen
(`pipeline/translation_pipeline/README.md`). Frozen translation and model-enrichment inputs are reused, not inferred again.
A seeded rebuild does not by itself guarantee identical bytes across dependency
versions; compare the generated manifest with the retained snapshot checksums.

Every generator accepts a `random.Random` instance or an integer `seed`.
No global RNG is used; do not rely on it.

Git ships the five large snapshots compressed (`pipeline/packing.py`, deterministic
gzip, readers untouched); `build_all` unpacks them first thing. A fresh clone therefore
needs only `build_all --force --from database` for the database, and `build_all --force`
to rebuild everything from the public dumps, which it downloads itself.

## Time frame

The behavioural layer keeps the real Amazon timestamps (orders 1999-12-01 to
2014-07-23). The substrate therefore has one "today":
`substrate.constants.SUBSTRATE_REFERENCE_DATE = 2014-07-23`, the day of the
last order. Ages are measured at that date, the seeded CRM notes fall into the
year before it, and anything downstream that needs purchase recency must count
from it, never from the wall clock (decision 2026-09-02; the alternative,
shifting the real order dates into the present, was rejected as an edit of
real data).

## What does _not_ live here

- **UC business logic** — `ucs/uc0X_*/`.
- **Generation wrappers** for LLM API calls — `utils/generation/`.
- **Per-UC snapshots** downstream of the substrate (for example UC-01's
  `ocean_inferred.json` or UC-04's category embeddings) — those stay
  co-located with their UC.

## Next step

- [schema/README.md](schema/README.md) — entity inventory + session helpers.
- [generators/README.md](generators/README.md) — the seeded data library.
- [pipeline/README.md](pipeline/README.md) — build chain, `build_all`, and per-script roles.
- [snapshots/README.md](snapshots/README.md) — every committed artifact and who reads it.
- Parent: [../README.md](../README.md).
