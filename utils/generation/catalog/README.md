# Model catalog

Generates the model menus the CLI adapters in `utils/generation/` validate against.
Nothing here runs when a model is called; the outputs are committed code.

Run the commands below from the repository root. Printing and checking use saved files; updating is a separate maintenance action that changes the catalog.

## Flow

```
codex   ~/.codex/models_cache.json ─┐
claude  alias map in the binary,   ├─ update ─► catalog.json ─► codegen ─► ../models.py
        `claude auth status` + docs │           (full record,               (menus only,
agy     live `agy models`          ─┘            provenance)                 imported by adapters)
models.dev  context / pricing / deprecated (enrichment, cached)
```

| Command | What it does |
| --- | --- |
| `python -m utils.generation.catalog` | Print the committed catalog: providers, vendor defaults, models with tiers, source statuses. |
| `python -m utils.generation.catalog update` | Regenerate `catalog.json` and `../models.py` from this machine. Validated, atomic, last-good on failure. |
| `python -m utils.generation.catalog update --render-only` | Re-render `../models.py` from the committed `catalog.json` (no CLI or network reads). |
| `python -m utils.generation.catalog check` | Exit 1 when `catalog.json` fails its schema or `../models.py` is stale. |

None of these prompts a model. A full `update` does launch provider CLI commands, including Claude, and reads the network; do not run it if those programs must remain unused. `agy models` and `claude auth status` are listings;
models.dev and the Claude docs page are public fetches with an ETag cache in
`.cache/` (gitignored).

## Files

| File | Role |
| --- | --- |
| `catalog.json` | Generated record, committed, never hand-edited. `generated_at` + `sources` = which CLI state the menus reflect. |
| `../models.py` | Generated Python module the adapters import (`CODEX_MODELS`, `CLAUDE_ALIASES`, `AGY_TIERS`, ...). |
| `overlay.toml` | The only hand-edited data file: curated fallbacks per provider, used when a source is unavailable. |
| `catalog.schema.json` | JSON Schema `catalog.json` must satisfy. |
| `__main__.py` | Print, update, render-only and check commands. |
| `codegen.py` | Deterministic rendering of `catalog.json` into `../models.py`. |
| `merge.py` | Assembles one catalog from the sources plus the overlay. |
| `validate.py` | Schema check plus alias / default consistency. |
| `detect.py` | Which provider CLIs are on PATH. |
| `sources/` | One reader per source: `codex_cache`, `claude_binary`, `claude_docs`, `agy_models`, `modelsdev`. |

## Rules

- **Thesis defaults live in `utils/generation/__init__.py`** (`DEFAULT_MODELS`), not
  here. The catalog's `default_model` is the vendor's menu default as observed when the catalog was generated and is exposed only as
  `*_VENDOR_DEFAULT` in `models.py`. `tests/utils/generation/test_models_generated.py`
  fails when a regeneration drops a model a thesis default names.
- **Regenerate, review the diff, commit both files.** A run folder records the
  concrete model id; the catalog's `generated_at` says which menu was in force.
- **A CLI missing on the regenerating machine keeps its rows** from the committed
  catalog (status `KEPT` in `sources`), so a partial machine never erases a provider.
  A provider that was never catalogued is dropped.
- **Any failure keeps last-good**: `catalog.json` and `models.py` are replaced only
  after validation, atomically.

Vendored from the author's `model-catalog` project (MIT); the loader, sources, merge
and validation are unchanged apart from package paths, the snapshot copies are
dropped, and the KEPT rule plus the codegen step are additions for this repository.
