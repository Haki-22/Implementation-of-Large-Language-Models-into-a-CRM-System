# UC-03 documentation

Operator-facing material for the UC-03 MCP server. Runtime artefacts (audit
logs, session maps) live under `../.runtime/`, not here.

```
docs/
├── README.md                          this file
└── mcp_client_config.example.json     registration template for an MCP host (Claude Desktop, Cursor, the Claude CLI)
```

## Registering the server in an MCP host

1. Copy the `uc03` block of `mcp_client_config.example.json` into the host's
   configuration and replace `<project_root>` with the absolute path of the
   repository root (any directory name) and `<python>` with the interpreter of the project
   virtualenv.
2. Choose the security profile in `UC03_SECURITY` (`strict` by default).
3. Restart the host; fifteen `uc03` tools appear. The first call under a masking
   profile creates the session map next to the audit log.

Under a masking profile, tool results contain tokens for structured fields and detected free-text entities. A bare MCP registration does not mask what you type directly into that host; use the UC-03 chat/GUI for user-turn masking. To see the answer with the values restored,
use the chat client (`python -m ucs.uc03_mcp_privacy.chat --provider codex`) or the browser
bridge, both of which hold the session map; a bare MCP host such as Claude
Desktop shows the tokens, which is exactly what the model saw.

## Related

- [UC-03 guide](../README.md) — the middleware, the profiles, the tool surface, the guarantees.
- [Demonstration scenario](../demo/scenario.md) — a scripted walkthrough for a live demonstration.
- [Evaluation overview](../eval/README.md) — the synthetic audio corpus and what its numbers mean.
