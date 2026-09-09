# thesis dm — the demo page

One page in the browser over the four prototypes and the repository. It is built on the
bridge in `bridge/` alone: every tab reads and runs the same functions the use-case CLIs
call, nothing is mocked in the page, and a failed call shows its error as a toast in the
corner. The page exists so
the practical part can be shown and read from one place: a person, a level, a message; a
text, its tokens, the restored text; a dictation, the tools the model chose, the audit
chain; a customer, the hidden purchase, each arm's list; and the repository's READMEs and
code in place.

## Structure

| File | Role |
| --- | --- |
| `index.html` | Loads React, ReactDOM, Babel, Lucide, marked and DOMPurify from a CDN at fixed versions; all except Lucide also have integrity hashes |
| `lib.jsx` | Shared helpers: fetch, settings kept in the browser, formatting, the level labels, the job poller, the toast store (`toast.error`), the page history hook (`usePageHistory`) |
| `components/Conversation.jsx` | `Chat` (bubbles with folds and meta lines, thread, composer), `Guide`, `ChatHead`, `UseCaseShell` |
| `components/PersonCard.jsx` | `PersonList` (search) and `PersonCard` (identity, orders, words, OCEAN, which rungs can run) |
| `components/Runs.jsx` | `RunPicker` over run folders, `MarkdownCard` (cards rendered from Markdown), `RowsTable`, `JobProgress` |
| `components/ModelPicker.jsx` | Provider → model → tier from the catalog; the active-model read-out of the top bar |
| `components/Bits.jsx` | `TokenMap`, `AuditTrail`, tool calls, check rows, sub-tabs, key/value rows, progress bar, `Toaster`, `PickerFold` (a picker folded to one line) |
| `Chrome.jsx` | The top bar: tabs, the LLM switch pill, the active model |
| `Settings.jsx` | The model for every tab, the whole catalog table, the LLM switch, the page history and its delete buttons |
| `Setup.jsx` | The installation screen: what a fresh clone lacks, the buttons that supply it, the job's log |
| `Uc01.jsx` … `Uc04.jsx` | One tab per use case; each composes the components above |
| `UcCode.jsx` | The repository browser (tree, READMEs, files, `git grep`) with the explainer beside it |
| `App.jsx` | Tab routing, the catalog, the settings, the switch |
| `kit.css`, `colors_and_type.css` | The styles (the design tokens and the kit; the 2026-09-07 section carries the shared components) |
| `bridge/` | The FastAPI backend that serves this page at `/dm/` and exposes every route below |

## How to use

Install the Python environment once (from the repository root):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .            # pinned requirements, packages on sys.path
```

Start the bridge and open the printed address:

```bash
./thesis-dm-frontend/bridge/run.sh                                  # http://127.0.0.1:8765/dm/
THESIS_DM_BRIDGE_PORT=8766 ./thesis-dm-frontend/bridge/run.sh       # another port
```

The page needs the bridge: it is served by it and reads everything from it. Model calls
are off until the switch in the top bar (or in Nastavení) is turned on; the mock provider
works for text-generation plumbing, not as an MCP host. The UC-03 chat needs the selected `claude`, `codex` or `agy` CLI on `PATH` (the MCP host); Whisper runs
locally for dictation.

On a fresh clone, use **Instalace** to start the setup job: it unpacks the compressed snapshots,
assembles the database and downloads the two local models, as a job with a log; the same
commands are listed on the screen for the command line. The tab stays reachable afterwards
(a full rebuild from the raw dumps, the model downloads, the CLI status).

The **Kód** tab can browse files without Git, but full-text search uses `git grep`
and requires indexed files. `git init` alone is not enough. Review `.gitignore`
and stage only intended publication files; do not add the local environment,
database, downloads, credentials or runtime logs. No initial commit is needed
for indexed search. See the [root guide](../README.md) before staging a fresh export.

## The tabs

| Tab | Left (choose and run) | Centre (chat) | Right (inspect) |
| --- | --- | --- | --- |
| **01 · Personalizace** | person (the pick, search over all), brief or own text, the ladder (tiers, arms folded) | the message, its judge verdict, prompt and slots in folds; the whole ladder as a job | the person card; run folders with a message browser; the results card |
| **02 · Pseudonymizace** | NER on/off, corpus samples, text, task | original → masked → the model's masked answer → restored | token map, results card, NER comparison, run folders, history |
| **03 · Hlas → CRM** | security profile (a change opens a new session), dictation (record or WAV), examples, the 15 tools | one session per window: answer, what the model saw, tool calls, latency | the session's audit chain with verification, the review queue, Whisper evaluation |
| **04 · Doporučování** | customer (the pick or the sample), protocol, classical arms, branches, regimes, model methods, sample limit | the hidden purchase against each arm's list, the model's lines for the customer | the customer card (same component as UC-01), run folders with cards and tables, the results card |
| **Kód** | the tracked tree (`git ls-files`), breadcrumbs, `git grep` | the file: READMEs rendered with relative links that navigate, code with line numbers | the explainer citing the open file (router, or a model over the first 200 lines) |
| **Instalace** | — | the checks (snapshots, database, models, raw dumps, CLIs) and the steps | the running job with its log |
| **Nastavení** | — | the LLM switch; provider, model and tier from the catalog; the whole catalog | the active configuration and the CLI status |

## Rules the page follows

- **Backend only.** No client-side fallback, no mock dataset; `index.html` opened from disk
  shows nothing useful.
- **One switch.** Every route that can reach a paid provider fails closed with HTTP 403
  while `THESIS_LLM_CALLS` is off for the bridge process; the pill in the top bar flips it.
- **Long runs are jobs.** The UC-01 ladder, the UC-04 arena and the UC-04 model methods run
  in the background; the page polls `/jobs/{id}` and reads the run folder when it ends.
- **UC experiment runs keep the saved records separate.** A UC-04 run from the page, classical or model,
  carries `role="comparison"` (record selection requires `role="record"`), and a model run
  also a sample limit; the UC-01 ladder from the page reuses the record's
  identical calls and writes its own folder; every page run refreshes its appendix files
  under `bridge/.runtime/attachments/`, never under `attachments/`; the UC-03 chat
  writes into a copy of `substrate.db` under `bridge/.runtime/` (`POST /uc03/reset-db`
  makes a fresh copy). Setup/rebuild actions are different: they can replace the shared database and regenerated snapshots.
- **One chat window = one session.** UC-03 keeps the conversation on the model host
  (Claude's session UUID or Codex/agy's returned conversation ID) and the envelope map across turns.
  Provider, model, tier and security profile are fixed per session; a changed selection
  opens a new one. Unsupported MCP providers are rejected without a fallback.
- **Models from the catalog.** Providers, models, tiers, prices and CLI status come from
  `utils/generation/catalog/catalog.json`; the page types nothing about models itself.
- **UC-01 judge is independent of the writer.** The Soudce picker defaults to free rules.
  Choose rules only (0), one judge (1), two judges (2), or two with conditional arbitration
  (3). Each role has its own provider, model and reasoning tier. Claude is disabled in this
  picker, including Claude models hosted by agy. The two judges use different providers;
  the arbiter may reuse a provider, which is not a third-provider comparison. Rules run
  first; models assess vocative, register and gender, not general factuality. Both routes
  accept `judge: {level, judges: [{provider, model, tier}, ...], arbiter: {provider, model, tier}}`
  (arbiter only at level 3), with separate call gating. The former single-model shape is
  still accepted. A ladder's judgment is a separate `judge-page-*` folder; messages and
  previous judgments are not overwritten. The text panel labels every selected stage:
  green valid, orange partial, red invalid; errors and unperformed stages are grey.
  The original HUMAN routing state and detailed evidence remain visible.

## Routes

| Route | Purpose |
| --- | --- |
| `GET /health` | readiness: database, pick, corpus, handoff, switch, the scratch database |
| `GET /generation/catalog`, `/generation/options` | the model catalog with prices and limits; the short menus |
| `GET/POST /llm-switch` | the process-wide model-call switch |
| `GET /jobs`, `GET /jobs/{id}` | background runs: state, progress, log tail, result |
| `GET /uc01/levels`, `/uc01/contacts`, `/uc01/contacts/{id}`, `/uc01/briefs` | the ladder, the people, the person card, the briefs |
| `POST /uc01/generate`, `POST /uc01/ladder` | one message (`generate()`); the ladder for one contact as a job |
| `GET /uc01/runs`, `/uc01/runs/{id}/messages`, `/uc01/results` | run folders, their messages, the card |
| `POST /uc02/mask`, `/uc02/restore`, `/uc02/roundtrip` | pseudonymize; restore; mask → model → restore (`with_envelope`) |
| `GET /uc02/samples`, `/uc02/results`, `/uc02/runs/{name}` | corpus rows; the cards and run folders |
| `POST /uc03/session`, `POST /uc03/chat` | open a session with fixed provider/model/tier; one turn (`chat.run_turn`, Claude/Codex/agy MCP host) |
| `GET /uc03/audit`, `/uc03/tools`, `/uc03/review`, `/uc03/results` | the session's chain; the 15 tools per profile; held changes; Whisper evaluation |
| `POST /uc03/transcribe`, `POST /uc03/reset-db` | WAV (16 kHz mono) → text through `stt.transcribe_pcm`; a fresh scratch database |
| `GET /uc04/arms`, `/uc04/runs`, `/uc04/runs/{name}`, `/uc04/results` | registries; run folders; one run's card, table, rows; the card |
| `GET /uc04/customers`, `/uc04/customers/{id}` | customers with the hidden item; one customer against every arm of a run |
| `POST /uc04/run`, `POST /uc04/model-run` | a classical run as a job; a model-method comparison on a sample as a job |
| `GET /setup/status`, `POST /setup/run`, `POST /setup/hf-token` | what a fresh clone lacks; the chosen steps (or a plan) as one job |
| `GET /repo/tree`, `/repo/file`, `/repo/search` | the tracked tree, one file, `git grep` |
| `GET /code/files`, `POST /code/ask` | the curated files; a question answered with a cited file (router or model) |

## Tests

`tests/frontend/test_bridge.py` runs the bridge with the FastAPI test client and the mock
provider: the catalog, the switch gates, the registries served as they are, UC-02 without a
model, the job lifecycle, the person card, a mock generation, the run folder readers, the
repository browser.

## Next step

- [Bridge guide](bridge/README.md) — the backend: one module per concern, the jobs, the rules.
- [Main README](../README.md) — the prototype the page demonstrates.
