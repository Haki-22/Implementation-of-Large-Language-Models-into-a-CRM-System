# Generation Utilities

`utils.generation` is the shared text-generation adapter used by the use-case
code. It provides one public API while hiding provider-specific CLI details.

## What it does

- routes calls to Codex, Claude, the Antigravity CLI (`agy`), or a deterministic mock provider
- provides a single text-or-JSON convenience API; every real provider takes the
  JSON Schema through its native CLI flag (`--output-schema` / `--json-schema`)
- validates model ids, aliases and tiers against the generated menu in
  `models.py` (see `catalog/README.md`); unknown menu values are refused locally; live availability still depends on the
  installed CLI and account
- normalizes provider errors into typed exceptions
- keeps provider-specific CLI behavior out of the UC modules
- fails closed unless the global model-call switch is on (`THESIS_LLM_CALLS`,
  see `utils/llm_switch.py`); the `mock` provider is exempt

## Public API

Complete the [root setup](../../README.md#quickstart). Commands run from the repository root; awaited examples belong inside an async function or notebook.

```python
from utils.generation import generate, generate_text, generate_json, list_options

text = await generate_text("Write a short Czech CRM message.", provider="mock")

structured = await generate_json(
    "Return a greeting.",
    {"type": "object", "properties": {"text": {"type": "string"}}},
    provider="mock",
)
```

`generate()` returns text when no schema is passed and parsed JSON when a
schema is passed. `list_options()["catalog"]` names the catalog generation the
menus were rendered from.

## Providers

| Provider | Module | Transport | Thesis default | Notes |
| --- | --- | --- | --- | --- |
| `codex` | `codex.py` | local `codex exec` CLI | `gpt-5.6-luna`, low | Default provider; tiers validated per model |
| `claude` | `claude.py` | local `claude -p` CLI | `sonnet`, low | Aliases resolve to the concrete id; native system prompt mode |
| `agy` | `agy.py` | local `agy -p` CLI | `gemini-3.8-flash`, low | Tier folds into the model id; replaces the retired `gemini` CLI |
| `mock` | `mock.py` | no subprocess | none | Deterministic offline test double |

The table describes this code snapshot, not guaranteed account access or current vendor pricing. A catalog entry does not prove that a live call will succeed; model-unavailable responses are reported separately from rate limits.

The thesis defaults are `DEFAULT_MODELS` in `__init__.py`; the vendors' own menu
defaults are the `*_VENDOR_DEFAULT` constants in `models.py`. Use
`list_options()` or the CLI below to inspect supported values.

## Command-line smoke test

```bash
python -m utils.generation.cli --list-options
python -m utils.generation.cli --provider mock --prompt "Say OK"
python -m utils.generation.catalog            # the committed model menus
```

Live provider checks require authenticated local CLIs. They are opt-in because
they may consume quota or cost money. UC-03 uses the separate MCP wrappers, not
this text-only API; see [UC-03 setup](../../ucs/uc03_mcp_privacy/README.md#agy-setup-and-limits)
for agy permissions. Mock text generation is not a mock MCP host.

## Layout

| Path | Role |
| --- | --- |
| `__init__.py` | Public API, thesis defaults, provider dispatch, retry loop |
| `models.py` | GENERATED model menus (ids, aliases, tiers) per provider |
| `catalog/` | The updater that regenerates `models.py` and `catalog.json` |
| `cli.py` | Small smoke-test CLI for direct operator checks |
| `errors.py` | Typed provider errors and stderr classifier |
| `codex.py` | Codex CLI adapter |
| `claude.py` | Claude CLI adapter |
| `claude_mcp.py`, `codex_mcp.py`, `agy_mcp.py` | MCP-host adapters for UC-03: tool configuration and conversation continuation |
| `agy.py` | Antigravity CLI adapter |
| `mock.py` | Deterministic offline provider |
| `api/vertex/` | Vertex Gemini API wrapper, not used for any reported number |
