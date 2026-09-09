# Utils

Shared helpers used across the thesis prototype. Modules in this package
stay generic and do not depend on a single use case.

## Structure

| Item | Role |
| --- | --- |
| `generation/` | Provider adapters (Claude, Codex, agy, mock) + public `generate_text` API. |
| `paths.py` | Canonical project-root and shared data paths. |
| `file_safety.py` | Overwrite guards for generated artifacts. |
| `promptmodel.py` | Versioned prompt-spec metadata model with reproducibility fields. |
| `text_hygiene.py` | Definition of unusual characters + scan/clean + audit CLI used by every substrate build step. |
| `czech_identifiers/` | Czech identifier formats in three parts — `patterns` (what one looks like), `validate` (whether its format/checksum passes), `generate` (make a fictional one). The substrate uses `generate`; UC-02's pseudonymiser uses `patterns` + `validate` on every message. See its README. |

## How to use

Run commands from the repository root after the [main setup](../README.md#quickstart). Awaited examples belong in an async application or notebook. The mock call below requires neither credentials nor a model.

```python
# Resolve canonical paths instead of hardcoding strings.
from utils.paths import THESIS_ROOT, SNAPSHOTS_DIR

# Dispatch a single LLM call through the unified API.
from utils.generation import generate_text
text = await generate_text(
    prompt="Pozdrav klienta v 5. pádě.",
    system_prompt="Jsi český CRM asistent.",
    provider="mock",          # or "codex" / "agy" / "claude"
    timeout=120,
)
```

Discover available providers / models from the command line:

```bash
python -m utils.generation.cli --list-options
```

Clean text the way every substrate build step does, or audit data files for
unusual characters (zero-width, mojibake, control characters, HTML entities):

```python
from utils.text_hygiene import clean_text
raw_title = "USB\u200b cable &amp; adapter"
title = clean_text(raw_title)                      # None when nothing readable is left
```

```bash
python -m utils.text_hygiene audit substrate/snapshots ucs --exclude intermediate/ --exclude provenance/ --fail-on-critical
```

This package is for:

- runtime helpers reused by multiple UCs
- shared provider dispatch and error handling
- path constants that keep scripts portable
- prompt catalog metadata with reproducibility fields

It is **not** for: UC-specific business logic, synthetic-data generation,
database assembly, or experiment logs.

## Outputs

Generation wrappers return values for the caller to persist. Some explicit helper
commands do write files: the catalog updater regenerates its menu, for example. Use
`file_safety.py` guards around any write that would overwrite a committed
snapshot.

## Testing

The normal test suite uses only the mock provider and is deterministic.
Live provider checks are opt-in and need the global model-call switch
(`utils/llm_switch.py`):

```bash
THESIS_LLM_CALLS=TRUE THESIS_LIVE_PROVIDERS=codex THESIS_LIVE_MODELS=default \
    python -m pytest tests/utils/generation/test_live_provider_matrix.py -q
```

The example deliberately selects only Codex. Do not omit the provider filter if other providers must remain unused.

## TODO / Known limitations

- **The Codex text adapter's native system-prompt mode raises `NotImplementedError`**
  by design. Only `system_prompt_mode="concat"` (single user prompt with the system prompt
  prepended) is wired today. This restriction concerns the text adapter's system prompt, not UC-03: its separate Codex MCP wrapper supports conversation continuation.

## Next step

- Parent overview: [../README.md](../README.md).
- Consumers of these helpers: [../ucs/README.md](../ucs/README.md).
- Data the helpers point at: [../substrate/README.md](../substrate/README.md).
