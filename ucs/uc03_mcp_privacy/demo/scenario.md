# UC-03 demo scenario

A scripted walkthrough for a live demonstration: the same request under the
`open` and the `strict` profile, then the things that must fail. Run everything
from the `thesis` directory with the switch on (`--force-llm`).

## Before the demo

```bash
./ucs/uc03_mcp_privacy/demo/run_demo.sh                 # strict, scratch copy of the database
./ucs/uc03_mcp_privacy/demo/run_demo.sh --security open
```

Both must end with `OK: every check passed`. The smoke never touches
`substrate.db`; the chat below does, so notes filed during the demo stay in the
database (with `author = llm:<model>`), which is the point.

## Step 1 — the same question in clear and masked

```bash
python -m ucs.uc03_mcp_privacy.chat --security open   --session demo-open   --show-model-view --force-llm \
    --text "Najdi kontakt Novák z Brna a řekni mi, co si naposledy objednal."
python -m ucs.uc03_mcp_privacy.chat --security strict --session demo-strict --show-model-view --force-llm \
    --text "Najdi kontakt Novák z Brna a řekni mi, co si naposledy objednal."
```

Compare the two `Tool calls` blocks: under `open` the model receives
`{"id": 409, "name": "Luboš Novák", "email": ...}`, under `strict` it receives
`{"id": "<CONTACT_2202>", "name": "<PERSON_9326>", ...}` and no e-mail at all.
The `Answer` line is the same for you, because the chat restores the tokens.

## Step 2 — dictate a note about a meeting

```bash
python -m ucs.uc03_mcp_privacy.chat --security strict --session demo-strict --show-model-view --force-llm --dictate
```

Say, for example: _"Byl jsem na schůzce s Emily z Chocolate Cake, koupila by, ale
není si jistá cenou. Nevidí hodnotu v našich recyklovatelných produktech, když je
koupí dvakrát levněji od Dunder Mifflin."_ Press Enter. What to point at:

- `The model saw:` — `<PERSON_…>` for Emily, `<ORG_…>` for both companies.
- `Tool calls:` — `search_contacts` with the tokens (the server searched in clear),
  and if several people match, the model asks you which one; then `create_note`
  with tokens in the text.
- `Answer:` — the names are back.
- The stored note: `python -m ucs.uc03_mcp_privacy.review list` shows nothing
  (notes are routine), but
  `sqlite3 substrate/snapshots/substrate.db "select content, author, audit_seq from uc_notes order by id desc limit 1"`
  shows the real text, the model as author, and the audit row it came from.

## Step 3 — a change that needs a person

> "Změň Emily telefon na 777 000 111."

The model passes the `updated_at` it read on the record. Under `strict` the response says `pending_review`. Show the queue and apply it (the queue tells you whether the field is still what the model saw):

```bash
python -m ucs.uc03_mcp_privacy.review list
python -m ucs.uc03_mcp_privacy.review apply <change_id>
```

Under `open` the same request is applied at once and still logged.

## Step 4 — what John says about headphones

> "Co říká Novák o sluchátkách?"

The model calls `search_reviews(query="sluchátka", contact_id=<CONTACT_…>)` over
the full-text index of 45 951 reviews and summarises; the review text reached it
with names masked.

## Step 5 — the audit trail

```bash
python -m ucs.uc03_mcp_privacy.audit_log verify  ucs/uc03_mcp_privacy/.runtime/sessions/demo-strict/audit.jsonl
python -m ucs.uc03_mcp_privacy.audit_log inspect ucs/uc03_mcp_privacy/.runtime/sessions/demo-strict/audit.jsonl
```

One row per call: tool, hash of the arguments, outcome, duration, the manifest
in force. Edit any row and run `verify` again: the chain breaks from that row on.

## What must not work

| Test                                                                                                 | Expected                                                               |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Edit a tool description in `server.py` and start the server                                          | `FATAL: tool manifest verification failed: changed=[...]`, exit code 1 |
| Copy `tool_manifest.json`, change one `sha256`, start with `UC03_MANIFEST_PATH` pointing at the copy | the same refusal                                                       |
| Under `masked` or `strict`, ask the model to run SQL | `query_sql` answers `disabled` |
| Under `masked`/`strict`, call `get_contact` with a plain number                                      | `bad_id`: ids are handles in this profile                              |
| Stop the UC-02 NER model from loading (e.g. an empty `HF_HOME`) and file a note without a category   | `envelope_unavailable`: the server refuses rather than send clear text |
| Change a row of the audit log                                                                        | `audit_log verify` reports the broken chain                            |
