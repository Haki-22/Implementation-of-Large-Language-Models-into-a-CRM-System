# UC-03 — MCP middleware with UC-02 masking at the protocol boundary

A language model talks to the CRM only through this server. It speaks the Model
Context Protocol (MCP) over stdio, exposes fifteen tools over the shared
`substrate.db`. Under the default security profile, structured personal fields
and row ids travel as session tokens, which the server resolves on the way back.
Free text uses UC-02 detection, so missed entities remain a leakage risk. Every call lands in a hash-chained audit log and the tool
definitions the model reads are pinned and verified before the server answers a
single request. A chat client sits on top: type a request or dictate it (local
Whisper), the model reads the tool descriptions and does the rest.

## Structure

```
ucs/uc03_mcp_privacy/
├── server.py               FastMCP stdio entry point: manifest check, audited dispatch, the tool descriptions
├── tools.py                the fifteen tools for one security profile (CrmTools): reads, writes, review queue
├── envelope.py             session envelope: value tokens, id handles, restore, the shared map file
├── audit_log.py            append-only hash-chained JSONL log; `verify` CLI
├── tool_manifest.py        pin of the advertised tools/list payload; `pin` / `verify` CLI
├── tool_manifest.json      the committed pin (re-pin after an intentional change, review the diff)
├── categorizer.py          note categoriser: keyword rules, or a model behind THESIS_LLM_CALLS
├── chat.py                 CLI chat: --text / --dictate / --file, Claude/Codex/agy CLI as the MCP host
├── stt.py                  speech to text: local faster-whisper (default), Google Web/Cloud (comparison)
├── review.py               review queue for field changes held under strict
├── mcp_client.py           blocking MCP client for scripts and tests
├── config.py               settings; every value environment-overridable
├── vocab_cs.txt            Czech CRM vocabulary given to Whisper as the initial prompt
├── demo/                   smoke.py + run_demo.sh (integration checks on a scratch database) + scenario.md
├── docs/                   MCP client registration template
├── eval/                   synthetic Czech audio corpus and the Whisper runs (see eval/README.md)
├── .runtime/               audit logs, session maps, MCP configs of local runs (gitignored)
└── models/                 faster-whisper cache (gitignored, several GB)
```

## Security profiles

One setting, `UC03_SECURITY`, selects how much of the security chapter the server
enforces. The audit chain and the manifest pin are on in every profile.

| Profile | What the model gets |
| --- | --- |
| `open` | The full interface: clear values, every column, `query_sql` for any read-only SELECT (bounded rows, cells and time), every write applied at once. The model is the whole integration layer. |
| `masked` | The interface without `query_sql`, plus the UC-02 envelope on every result and every write argument: structured columns tokenised by schema, free text by the UC-02 detector, row ids as random handles. Fails closed. |
| `strict` | `masked` plus scope: contact and company records carry only the fields an assistant needs (no personality profile, no bank data, no birth date), `query_sql` is off, field changes are held for review. |

`strict` is the default. It is not read-only: note creation, updates and deletion are applied immediately; contact/company field changes wait for review.

## The tool surface

| Tool | Kind | Notes |
| --- | --- | --- |
| `ping`, `server_info`, `whoami` | infra | liveness, metadata (includes the active profile), identity |
| `search_contacts(query, company, limit)` | read | every word must match first name, last name, e-mail, phone, city or employer, a declined name form counts (Petru Bartošovi finds Petr Bartoš: UC-02 stem, then a two-letter ending tolerance); returns id, name, company, city, lifecycle stage, note count, last order |
| `get_contact(contact_id, include_notes, …)` | read | the record with the employer and recent notes |
| `get_company(company_id, contact_limit)` | read | identifiers, address, the people employed there |
| `search_notes(query, contact_id, limit)` | read | newest first |
| `search_reviews(query, contact_id, limit)` | read | FTS5 over 45 951 reviews, Czech and English; "what does John say about headphones" |
| `list_orders(contact_id, limit)` | read | purchases, newest first |
| `query_sql(sql, limit)` | read | one SELECT on a read-only connection, `open` only: a column-name policy cannot mask arbitrary SQL, so `masked` and `strict` answer `disabled` |
| `create_note(contact_id, content, category)` | write | tokens restored before storing; category validated or assigned by the categoriser from the masked text |
| `update_note`, `delete_note` | write | name the note's `updated_at` you read; applied in every profile, logged in `uc_change_log` |
| `update_contact(contact_id, field, value, expected_updated_at)` | write | allow-listed fields; the stamp you read must still be current, else `stale` with the current value; **held for review under `strict`**, applied and logged otherwise |
| `update_company(company_id, field, value, expected_updated_at)` | write | same rules |

Every write records **who** (`author`: `human`, or `llm:<model>` from `UC03_AUTHOR`)
and **which call** (`audit_seq`, the row of the audit chain). A field change is a
`uc_change_log` row with the old and the new value.

**Every update names the version it read.** Contacts, companies and notes carry
`updated_at` (`null` until the server first writes the row, a new timestamp on
every write). Each `update_*` / `delete_note` call passes the `updated_at` the
model read back as `expected_updated_at`. If the row moved in between, the server
answers `stale` with the field's current value (masked like any other result)
and writes nothing; the model shows the value to the user and asks before
retrying with the current stamp. A held change under `strict` carries the same
stamp and is applied only while the row still has it; otherwise the queue closes
it as `conflict` and shows the reviewer what is there now.

## How the envelope works

The chat client and the server share one session map, a JSON file under
`.runtime/`. Take the sentence a salesperson dictates after a meeting:

```
you:    Byl jsem na schůzce s Emily z Chocolate Cake, nevidí hodnotu proti Dunder Mifflin.
model:  Byl jsem na schůzce s <PERSON_4127> z <ORG_388>, nevidí hodnotu proti <ORG_9051>.
model:  search_contacts(query="<PERSON_4127>", company="<ORG_388>")
server: restores the tokens, searches in clear, answers with tokens:
        [{"id": "<CONTACT_2202>", "name": "<PERSON_9326>", "city": "<ADDRESS_642>", ...}]
model:  create_note("<CONTACT_2202>", "Schůzka s <PERSON_4127> z <ORG_388>: ...")
server: restores every token -> the note in the database reads "Schůzka s Emily z Chocolate Cake: ..."
you:    see the model's answer with the names restored
```

In this example, the detected names stayed local; the database stores their restored values. Tokens are
UC-02's `<TYPE_n>` with random numbers unique per session (a number leaks
neither order nor row id); a person keeps one number across spellings, with a
letter suffix per form. Values the server knows by schema (name, e-mail, phone,
every address part down to the region, birth date, bank data, company name, IČO)
are masked without any detector; the model tells namesakes apart by company,
lifecycle stage and last order, and the chat restores the city for you; free text (note bodies, prior interactions, reviews, your own turn)
goes through UC-02's rules + NER. When the NER layer cannot run, the tool
refuses instead of sending clear text (fail closed). Under `open` the same
dialogue runs in clear, which is the side-by-side the thesis needs.

At tool input and final-answer restoration, known HTML-encoded token delimiters
are normalised locally. Unknown tokens and recognised damaged token spellings
produce an explicit error, not an empty search or a partially restored note.
`PERSON` value tokens are search terms; `CONTACT` handles identify database rows.
A surname token need not equal a returned full-name token: their random numbers
are not search scores or identity evidence. Multiple candidates require clarification.
Validation cannot detect every possible rewrite, a completely omitted token, or
a substitution with another valid token. An invalid final answer is flagged without
automatically replaying the turn: a tool may already have performed a write.

## How to use

All commands from the repository root with the project virtualenv active.
First complete the [root setup](../../README.md#quickstart). To assemble the database from shipped snapshots, use `python -m substrate.pipeline.build_all --force --from database`. `--verify` checks the existing build and may unpack shipped snapshots; it does not build the database.

These commands are independent examples. A standalone server waits for an MCP client. Chat and review commands can change the configured database; `review apply` approves a queued change. Use a scratch database (`UC03_DB_PATH`) for write experiments. The `open` profile sends clear values.

```bash
# The server (an MCP host normally spawns it; profile from UC03_SECURITY, default strict)
python -m ucs.uc03_mcp_privacy.server
python -m ucs.uc03_mcp_privacy.server --security open

# The chat (needs the switch: --force-llm or THESIS_LLM_CALLS=TRUE)
python -m ucs.uc03_mcp_privacy.chat --provider codex --text "Najdi kontakt Novák a shrň jeho poznámky" --force-llm
python -m ucs.uc03_mcp_privacy.chat --provider codex --model gpt-5.6-luna --tier low --text "Najdi kontakt Sedláček" --force-llm
python -m ucs.uc03_mcp_privacy.chat --provider codex --dictate --force-llm                 # Enter stops the recording
python -m ucs.uc03_mcp_privacy.chat --provider codex --file clip.wav --security open --force-llm
python -m ucs.uc03_mcp_privacy.chat --provider codex --text "..." --session demo1 --show-model-view

# Speech to text alone (local Whisper by default; google-web / google-cloud behind the switch)
python -m ucs.uc03_mcp_privacy.stt --record --seconds 20
python -m ucs.uc03_mcp_privacy.stt --file clip.wav --backend whisper --model large-v3-turbo

# The demo smoke: integration checks against a scratch copy of the database
./ucs/uc03_mcp_privacy/demo/run_demo.sh            # strict
./ucs/uc03_mcp_privacy/demo/run_demo.sh --security open

# Review queue (changes held under strict)
python -m ucs.uc03_mcp_privacy.review list
python -m ucs.uc03_mcp_privacy.review apply 3

# Audit chain and manifest
python -m ucs.uc03_mcp_privacy.audit_log verify ucs/uc03_mcp_privacy/.runtime/sessions/<id>/audit.jsonl
python -m ucs.uc03_mcp_privacy.tool_manifest verify
python -m ucs.uc03_mcp_privacy.tool_manifest pin       # after an intentional tool change

# Tests (see below)
pytest tests/ucs/uc03_mcp_privacy -q
```

To register the server in another MCP host (Claude Desktop, Cursor), adapt
`docs/mcp_client_config.example.json`. The browser demo of `thesis-dm-frontend/`
spawns the same server through `bridge/run.sh`, masks the typed turn and restores
the answer with the same envelope.

The browser fixes the selected provider, model and reasoning tier for each new
session; changing settings opens a new conversation. Claude, Codex and agy are the
available MCP hosts. Other providers are rejected explicitly, with no silent fallback.
UC-01, UC-02 and UC-04 use the separate text-generation
dispatcher; their provider support does not establish MCP-host support.

All three `utils.generation.*_mcp.generate_with_mcp` adapters share the Claude adapter's
call signature and return `text`, `tool_calls`, `session_id` and `raw`. They reuse their
existing CLI dispatchers rather than implementing another subprocess layer. The host-specific
parts are tool configuration and conversation flags. Built-in shell/file tools are disabled
by default. Hosts without tool events in their response use the UC-03 server audit for the
turn's observed calls; an empty tool-event list is not proof that no tools ran.

### agy setup and limits

The agy adapter creates a private workspace beneath the session folder, with an explicit
primary agent (`tools: []`, `inheritMcp: true`, `commandExecutionPolicy: off`). It discovers
the pinned server's tool inventory and converts the common allow-list into `disabledTools`;
unrelated global MCP servers are disabled in the workspace configuration. The token map and
database stay outside that workspace. Resume uses the returned `conversation_id`.

agy also requires operator-approved MCP permissions. Its
[permission settings](https://antigravity.google/docs/cli/permissions) use exact entries such
as `mcp(uc03/search_contacts)` and `mcp(uc03/list_orders)` in `permissions.allow` under
`~/.gemini/antigravity-cli/settings.json`. Grant only the tools intended for the deployment;
the adapter does not change that file or use `--dangerously-skip-permissions`. Write tools
need their own permission; a read-only grant does not enable note or field changes. Profile
restrictions and the server audit still apply independently of host permissions.

A 2026-09-08 read-only probe with agy/Gemini 3.8 Flash retrieved the matching contact and
last purchase with a valid audit and unchanged scratch database, including with the MCP-only
primary agent. This is a connectivity smoke test, not a security benchmark. The exported evidence does not include a preserved multi-turn connectivity benchmark;
wrapper routing and continuation also have offline test coverage.

## What the audit log and the manifest guarantee

**Audit log.** One row per tool call: sequence, time, tool, SHA-256 of the
arguments (never the arguments), outcome (`ok` / `refused` / `error`), duration,
the SHA-256 of the manifest in force, and the chain hashes. The row is reserved
before the tool runs and written when it ends, under a file lock, so several
servers can share one log and a note's `audit_seq` always names its own call.
Changing or removing a row that has a successor breaks the chain from that point
on; `audit_log verify` re-walks it. Cutting the tail is not detectable from the
file alone: keep the last hash somewhere else (the chat prints it) when that
matters. An attacker able to rewrite the log can also recompute its hashes; the
chain alone does not authenticate an untrusted file.

**Manifest.** The pin covers the whole payload the server advertises for each
tool in `tools/list` (name, description, input schema, and any title, output
schema or annotations the SDK adds). It is committed with the code, so a fresh
checkout verifies against what the author pinned. A changed, missing or **new**
tool stops the server before it answers; under the `strict` profile this cannot
be switched off, under `open` and `masked` `UC03_MANIFEST_STRICT=0` is the
development escape hatch. The pin is a fingerprint the author re-computes after
an intentional change, not a cryptographic signature: it detects silent drift,
it does not authenticate the author.

## Environment

| Variable | Default | Effect |
| --- | --- | --- |
| `UC03_SECURITY` | `strict` | `open` / `masked` / `strict` |
| `UC03_DB_PATH` | `substrate/snapshots/substrate.db` | the CRM database |
| `UC03_RUNTIME_DIR` | `ucs/uc03_mcp_privacy/.runtime` | audit logs, session maps, MCP configs of local runs |
| `UC03_AUDIT_PATH` | `<runtime>/audit.jsonl` | audit log of this server instance |
| `UC03_SESSION_MAP` | `<runtime>/session-map.json` | the envelope file shared by the chat client and the server |
| `UC03_MANIFEST_PATH` | `ucs/uc03_mcp_privacy/tool_manifest.json` | the pin to verify against (tests point it elsewhere) |
| `UC03_MANIFEST_STRICT` | `1` | `0` lets the server start on a mismatch under `open`/`masked` only |
| `UC03_AUTHOR` | `llm` | `author` of every write through this instance (`llm:<model>`) |
| `UC03_WHISPER_MODEL` | `medium` | faster-whisper size for dictation (`tiny` … `large-v3-turbo`) |
| `UC03_STT_BACKEND` | `whisper` | `whisper` / `google-web` / `google-cloud` |
| `UC03_MODEL_DIR` | `ucs/uc03_mcp_privacy/models` | faster-whisper download cache |
| `UC03_WHISPER_DEVICE`, `UC03_WHISPER_COMPUTE_TYPE`, `UC03_WHISPER_BEAM_SIZE`, `UC03_WHISPER_LANGUAGE`, `UC03_WHISPER_VOCAB_FILE` | `cpu`, `int8`, `5`, `cs`, `vocab_cs.txt` | Whisper decoding settings |
| `UC03_RECORD_MAX_SECONDS` | `60` | upper bound of one push-to-talk recording |
| `UC03_GOOGLE_WEB_LANGUAGE`, `UC03_GOOGLE_CLOUD_LOCATION`, `UC03_GOOGLE_CLOUD_RECOGNIZER`, `UC03_GOOGLE_CLOUD_MODEL`, `UC03_GOOGLE_CLOUD_LANGUAGE`, `GOOGLE_CLOUD_PROJECT` | `cs-CZ`, `global`, `_`, `latest_long`, `cs-CZ`, unset | the two Google backends (comparison only) |
| `THESIS_LLM_CALLS` | `FALSE` | the global switch; the chat, the model categoriser and cloud STT need it on |

## Outputs

- **CRM data** — notes and field changes in `substrate.db` (`uc_notes.author`, `uc_notes.audit_seq`, `uc_change_log`).
- **Audit log** — `.runtime/…/audit.jsonl`, one hash-chained row per call.
- **Session map** — `.runtime/…/session-map.json`, the token map of one session; local only.
- **Chat report** — `chat.py --json` prints what you said, what the model saw, the tool calls, the answer and the audit verdict.

## Evaluation

`eval/synth/` holds a 20-clip synthetic Czech dictation corpus and two Whisper
runs (medium, large-v3-turbo) with word error rate, survival of the personal
data in the transcript and categoriser accuracy; `eval/README.md` says what each
number is and is not. The evaluation of the middleware itself (tool-call
accuracy on scripted dictations against the expected database state, a leak
check on everything the model saw, latency per call) is the next step and has
not run yet; no number about it is claimed anywhere.

## Relationship to the other parts

- **UC-02** is imported, not copied: `envelope.py` builds on `detect_rule_based`,
  `detect_ner`, `merge_spans`, `entity_key` and the token vocabulary of
  `ucs.uc02_pseudonymization`. What UC-02 evaluates as a message-level envelope,
  UC-03 applies at the protocol boundary.
- **The substrate** provides the database and the note categories
  (`substrate.constants.NOTE_CATEGORIES`); the server reads it through `sqlite3`
  so it imports in milliseconds.
- **The frontend bridge** (`thesis-dm-frontend/bridge/`) is a thin HTTP layer
  over the same chat flow.

## Tests

```bash
pytest tests/ucs/uc03_mcp_privacy -q      # offline unit/integration coverage; cached Whisper is optional
```

`test_envelope.py` covers tokens, handles, restore, two writers on one map and
the fail-closed path with a stub detector. `test_tools_profiles.py` runs every
tool against a scratch database under the three profiles; its masking tests
share one invariant, no planted value (name, e-mail, phone, every address part,
IBAN, birth date, company name, IČO) appears anywhere in a result. It also
covers the version stamp (`stale`, the review `conflict`, an edit made and
reverted), the held-change queue and the structured refusals. `test_manifest.py`
checks that the committed pin matches the code and that drift in any advertised
field fails closed. `test_audit.py` covers the chain rule, the reserved row,
two writers on one file and tamper detection. `test_server.py` spawns the real
server over stdio with the committed pin and strict verification on, under
`strict` and `open`, and proves a tampered pin stops it. `test_stt.py` covers
the WAV checks and the switch on the cloud backends; the Whisper test runs only
when the tiny model is cached.

## External dependencies

`mcp==1.27.1` (pinned in `requirements.txt`), `faster-whisper`, a Claude/Codex/agy CLI on
`PATH` for the chat, PulseAudio's `parec` for dictation from the microphone,
and the UC-02 NER model (downloaded on first use) for the masking profiles.
