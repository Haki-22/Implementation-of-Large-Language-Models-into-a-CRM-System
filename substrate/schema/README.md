# `substrate/schema/` — shared SQLModel layer

The single source of truth for the CRM entity shapes. Imported as
`substrate.schema.*`.

The database holds **CRM content**: contacts, their notes, their employer, the
catalogue, the purchase history, the reviews behind it in both languages, and
the operator's message briefs. Evaluation inputs and results stay in committed
JSON/CSV, so the thesis numbers reproduce without this gitignored database
(see [DB.md](DB.md)).

## Structure

| File | Role |
| --- | --- |
| `models.py` | The twelve `SQLModel` entities + the `ErrorType` enum. |
| `session.py` | Async session factory (`init_db`, `get_session`); engine targets `substrate/snapshots/substrate.db`. |
| `__init__.py` | Re-exports the entities + the session helpers for clean imports. |
| `DB.md` | Entity inventory + cross-UC reuse notes + schema-evolution rules. |

Entities: `Contact`, `Note`, `Company`, `Product`, `Order`, `Review`,
`MessageBrief`, `ChangeLog`, `LifecycleStage`, `Recommendation`, `Topic`,
`Aspect`. `ErrorType` is the UC-01 error taxonomy, an enum rather than a
table. The FTS5 index `uc_reviews_fts` over the review text is a virtual table
the assembler builds, not an entity. See `DB.md` for row counts, readers, fill
rates and the cross-UC reuse contract.

## How to use

Run from the repository root after [building the database](../README.md#rebuild-from-scratch). `get_session()` yields a SQLAlchemy `AsyncSession`, so queries use `execute()` rather than SQLModel's `exec()`.

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

The prototype has no Alembic; rebuild the database from JSON snapshots
after any schema change:

```bash
python -m substrate.pipeline.build_all --force --from database   # canonical, ~45 s incl. audit gate + manifest
python -m substrate.pipeline.build_substrate_db --force            # the same step on its own, ~15 s
```

`models.py` and the JSON snapshots are versioned; `substrate.db` itself
is gitignored as a build artifact.

## Outputs

This module is import-only; it does not write to disk on import. The `init_db()` in `session.py`, which
creates the SQLite database at `substrate/snapshots/substrate.db` (path
resolved via `utils.paths.SUBSTRATE_DB`) if it does not yet exist.

## Next step

- [Substrate overview](../README.md) — substrate overview.
- [Database schema](DB.md) — full entity inventory, cross-UC ownership table, and
  schema-evolution rules.
- `../pipeline/build_substrate_db.py` — the canonical builder that
  populates these entities from committed JSON snapshots.
