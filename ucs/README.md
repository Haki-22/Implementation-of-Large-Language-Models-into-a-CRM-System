# Use Cases

The four thesis use-case packages. Each one is a self-contained
implementation that reads the shared substrate and writes its own snapshots
and evaluation outputs.

## Structure

| Package | Theme |
| --- | --- |
| `uc01_personalization/` | Czech CRM outreach personalization (L0–L6 ladder and single-signal arms). |
| `uc02_pseudonymization/` | Reversible Czech PII masking around LLM calls. |
| `uc03_mcp_privacy/` | MCP middleware between the CRM database and a chat: UC-02 masking at the protocol boundary, audit chain, pinned tool manifest, dictation. |
| `uc04_matchmaker/` | Recommender arena: twelve classical arms and five model methods on the CRM database, two protocols, two data regimes. |

## How to use

Complete the [root setup](../README.md#quickstart), then run these commands from the repository root. They are independent examples, not an installation script.

```bash
# UC-01 single-message demo
python -m ucs.uc01_personalization generate --contact 11 --brief 26 --level 1

# UC-02 evaluation suite
pytest tests/ucs/uc02_pseudonymization/ -q

# UC-03 MCP server
python -m ucs.uc03_mcp_privacy.server

# UC-04 arena (all fast classical arms, both branches, both protocols)
python -m ucs.uc04_matchmaker run --arms fast
python -m ucs.uc04_matchmaker model-run --provider mock --limit 3   # the model methods, plumbing only; real providers need --force-llm
```

The shared CRM database is `substrate/snapshots/substrate.db`. UC-02 can also mask text and score its saved corpus without the database. Use shared helpers
from `utils/`; do not copy database, generation, or synthetic-data code
into individual UC folders.

## Outputs

Per-UC snapshots live next to each package:

- `uc01_personalization/snapshots/` — generated messages + evaluation records.
- `uc02_pseudonymization/snapshots/` — source corpus, gold spans and generation manifests; evaluation results are in `eval/runs/`.
- `uc03_mcp_privacy/.runtime/` — audit logs, session maps and MCP configs of local runs (gitignored).
- `uc04_matchmaker/eval/runs/` — run folders with the arena's numbers; `results/uc04_to_uc01_handoff.json` — the handoff the database build loads for UC-01.

## Next step

- Open the UC README of interest: `uc01_personalization/README.md`, `uc02_pseudonymization/README.md`, `uc03_mcp_privacy/README.md`, `uc04_matchmaker/README.md`.
- Substrate the UCs read from: [../substrate/README.md](../substrate/README.md).
- Shared helpers: [../utils/README.md](../utils/README.md).
