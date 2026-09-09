# The bridge — the backend of the demo page

A FastAPI process that serves the page at `/dm/` and exposes one route module per concern.
Every route calls the plain function the use-case CLI calls (`pseudonymize`, `run_turn`,
`generate`, `runner.run`, `arena.run`, `model_arena.run`), so the page and the command
line are the same code path; the bridge adds HTTP validation and job/session management, with model dispatch through
`utils/generation/`. Installation streams the documented
`python -m substrate.pipeline.build_all` command into its job log.

## Structure

```
bridge/
├── app.py                the app shell: routers, /health, the static mount of the page
├── common.py             paths, the model-call gate (403 when the switch is off), error mapping, the database, run folders
├── jobs.py               background runs: registry, one job per kind, progress, log tail, GET /jobs
├── routes_generation.py  the model catalog (catalog.json + thesis defaults + CLI status), the switch
├── routes_uc01.py        levels, contacts, the person card, briefs, generate, the ladder job, run folders
├── routes_uc02.py        mask, restore, the sandwich with a model, samples, cards and run folders
├── routes_uc03.py        sessions kept across turns, chat, audit, tools, dictation, review queue, the scratch database
├── routes_uc04.py        arms and methods, arena and model-method jobs, run folders, customers against the arms
├── routes_repo.py        the tracked tree (git ls-files), one file, git grep
├── routes_code.py        the curated files and the explainer (router, or a model over the open file)
├── routes_setup.py       the installation screen: the checks of a fresh clone, the steps as one job
├── run.sh                the launcher (port, python, the manifest pin flag)
└── .runtime/             scratch: attachments of page runs, uploads, the UC-03 scratch database (gitignored)
```

## How to use

```bash
# From the repository root with the project virtualenv active.
./thesis-dm-frontend/bridge/run.sh                                  # http://127.0.0.1:8765/dm/
```

`run.sh` picks the active virtualenv's Python, warns when none of the `claude`, `codex` or `agy` CLIs is on PATH (UC-03 needs one supported MCP host), sets `UC03_MANIFEST_STRICT=1` so a UC-03 server
refuses to start on a changed tool, and runs uvicorn. Stop with Ctrl-C.

## What the routes guarantee

- **Fail closed on money.** `common.require_llm_calls_on` answers 403 while
  `THESIS_LLM_CALLS` is off for this process; the mock provider passes. `POST /llm-switch`
  flips it for the process only (never edits `.env`).
- **Jobs, not long requests.** A runner that takes minutes starts in a worker thread;
  `GET /jobs/{id}` reports state, `done/total` (from the runner's progress callback, or a
  probe over the run folder), the log lines the runner emitted, and the result (the run
  folder). One job at a time per kind (409 otherwise).
- **UC runs keep records separate.** Page runs refresh attachments under
  `.runtime/attachments/`; UC-04 runs from the page, classical and model, are
  `role="comparison"` (record selection requires `role="record"`), model runs also with a
  sample limit; the UC-01 ladder from the page reuses the record's identical calls into its
  own folder; the UC-03 chat writes into `.runtime/uc03-substrate.db`, a copy of the record
  database made on first use (`POST /uc03/reset-db` renews it). Setup/rebuild actions can replace the shared database and regenerated snapshots.
- **One session, one conversation.** `POST /uc03/session` returns a UUID; every turn of that
  session passes it to `chat.run_turn`, which uses the selected Claude, Codex or agy MCP wrapper and its continuation identifier. It keeps the envelope map of the session folder, so the
  model sees the earlier turns and a token means the same value throughout. The audit chain records the turn's observed server calls even when a host omits tool events from its response.
- **The page remembers; the runs do not care.** `PUT /history/{tab}` keeps the thread and
  the last choices of a tab under `.runtime/history/` (one JSON per tab, the last 200
  turns); `GET /history/{tab}` gives them back when the tab opens; `DELETE /history` and
  `DELETE /history/{tab}` are the delete buttons of the settings screen. The files never
  feed a run folder or an attachment.
- **The tree is git's.** `routes_repo` lists `git ls-files`, so the browser shows exactly
  what the public repository holds and never the runtime folders; without git it walks the
  folder minus the ignored names. Search still requires Git-indexed files: `git init` alone does not populate the index. Review ignore rules before staging; an initial commit is not required. Every path is checked to stay inside the repository root.

## Lifecycle

Jobs and sessions live in the bridge process's memory: a restart forgets them, the run
folders on disk stay. The registry keeps the last 50 finished jobs. A session is issued
by `POST /uc03/session` with a fixed profile and model; its turns are serialized by a
per-session lock, a second turn while one runs answers 409, and the scratch database is
not reset while a turn is in flight. The installation is an exclusive job: it waits for
running jobs and blocks jobs and model turns until it ends. "Run of record" for UC-04
means the newest folder that covers every arm and was launched as a record.

## Tests

`tests/frontend/test_bridge.py`: `pytest tests/frontend -q` from the repository root.

## Next step

- [Frontend guide](../README.md) — the page these routes serve, tab by tab, and the full route table.
