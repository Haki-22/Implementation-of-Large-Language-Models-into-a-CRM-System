"""Demo smoke: the guarantees of the README checked against a running server.

Spawns the MCP server (the same command a model host uses), drives the
canonical walk through the CRM tools, and checks after every step what the
README promises: tokens instead of values under a masking profile, restore on
write, provenance on the note, held field changes under strict, a valid audit
chain, a session map on disk. By default it runs against a **scratch copy** of
the CRM database under ``.runtime/demo/`` so a rehearsal never touches
``substrate.db``.

    python -m ucs.uc03_mcp_privacy.demo.smoke                  # strict
    python -m ucs.uc03_mcp_privacy.demo.smoke --security open
    python -m ucs.uc03_mcp_privacy.demo.smoke --db path/to.db  # a database of your own

Exit code 0 when every check passed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from ucs.uc03_mcp_privacy import config
from ucs.uc03_mcp_privacy.audit_log import AuditLog, verify
from ucs.uc03_mcp_privacy.mcp_client import McpStdioClient
from ucs.uc03_mcp_privacy.tools import TOOL_NAMES

DEMO_NEEDLE = "Novák"


class Check:
    """Collects pass/fail lines and the final verdict."""

    def __init__(self) -> None:
        """Start with no failures recorded."""
        self.failures: list[str] = []

    def __call__(self, condition: bool, label: str) -> None:
        """Print `label`'s pass/fail line and record it as a failure when `condition` is false."""
        print(f"  [{'ok' if condition else 'FAIL'}] {label}")
        if not condition:
            self.failures.append(label)


def _row_values(db: Path, contact_pk: int) -> list[str]:
    """The clear personal values of one contact row, to search for in tool results."""
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM uc_contacts WHERE id = ?", (contact_pk,)).fetchone()
    values = [
        str(row[col])
        for col in (
            "first_name",
            "last_name",
            "email",
            "phone",
            "full_street",
            "city",
            "iban",
            "bank_account",
        )
        if row[col]
    ]
    return values


def _leaks(payload: Any, values: list[str]) -> list[str]:
    """Return the `values` (3+ characters) that appear verbatim in the JSON dump of `payload`."""
    blob = json.dumps(payload, ensure_ascii=False)
    return [v for v in values if len(v) >= 3 and v in blob]


def run(profile: str, db: Path, runtime: Path) -> int:
    """Drive the server through the walk and check every guarantee; return the exit code."""
    runtime.mkdir(parents=True, exist_ok=True)
    audit_path = runtime / "audit.jsonl"
    map_path = runtime / "session-map.json"
    for stale in (audit_path, map_path):
        stale.unlink(missing_ok=True)
    env = {
        "UC03_DB_PATH": str(db),
        "UC03_AUDIT_PATH": str(audit_path),
        "UC03_SESSION_MAP": str(map_path),
        config.ENV_SECURITY: profile,
        "UC03_AUTHOR": "llm:demo",
    }
    masking = profile != "open"
    check = Check()
    print(f"UC-03 demo smoke · profile {profile} · db {db}")

    with McpStdioClient(env=env) as client:
        names = [t["name"] for t in client.list_tools()]
        check(
            names == list(TOOL_NAMES), f"tools/list advertises the {len(TOOL_NAMES)} tools in order"
        )

        found = client.call_tool("search_contacts", {"query": DEMO_NEEDLE, "limit": 5})
        check(
            found.get("ok") and found["count"] >= 1,
            f"search_contacts('{DEMO_NEEDLE}') finds a contact",
        )
        first = found["contacts"][0]
        ident = first["id"]
        check(
            (isinstance(ident, str) and ident.startswith("<CONTACT_"))
            if masking
            else isinstance(ident, int),
            "contact id is a session handle under masking, the row id under open",
        )
        # Resolve the row id ourselves through the session map to read the clear values.
        if masking:
            handles = json.loads(map_path.read_text(encoding="utf-8"))["handles"]
            contact_pk = int(next(ref for ref, h in handles.items() if h == ident).split(":")[1])
        else:
            contact_pk = int(ident)
        clear_values = _row_values(db, contact_pk)

        record = client.call_tool("get_contact", {"contact_id": ident, "note_limit": 3})
        check(record.get("ok"), "get_contact returns the record")
        if masking:
            check(
                not _leaks(record, clear_values),
                "no clear personal value of the row in get_contact",
            )
            check(
                not _leaks(found, clear_values),
                "no clear personal value of the row in search_contacts",
            )
        if profile == "strict":
            check(
                "ocean" not in record["contact"],
                "strict scope: no personality profile in the record",
            )

        name = record["contact"]["name"]
        note = client.call_tool(
            "create_note",
            {
                "contact_id": ident,
                "content": f"Volal {name}, chce reklamaci sluchátek, zavolat zítra.",
            },
        )
        check(note.get("ok"), "create_note files the note")
        stored = (
            sqlite3.connect(db)
            .execute("SELECT content, author, audit_seq FROM uc_notes ORDER BY id DESC LIMIT 1")
            .fetchone()
        )
        check(
            stored is not None and clear_values[0] in stored[0],
            "the stored note carries the real name",
        )
        check(
            stored is not None and stored[1] == "llm:demo" and stored[2] is not None,
            "author and audit_seq recorded",
        )
        check(
            note.get("category")
            in ("complaint", "follow_up", "general", "support", "sales", "delivery"),
            f"categorised as {note.get('category')}",
        )

        notes = client.call_tool("search_notes", {"query": "reklamaci", "contact_id": ident})
        check(notes.get("ok") and notes["count"] >= 1, "search_notes finds the note again")
        if masking:
            check(not _leaks(notes, clear_values), "no clear personal value in search_notes")

        change = client.call_tool(
            "update_contact",
            {
                "contact_id": ident,
                "field": "city",
                "value": "Brno",
                "expected_updated_at": record["contact"]["updated_at"],
            },
        )
        stale = client.call_tool(
            "update_contact",
            {
                "contact_id": ident,
                "field": "city",
                "value": "Brno",
                "expected_updated_at": "1999-01-01 00:00:00.000000",
            },
        )
        check(stale.get("error") == "stale", "a stale updated_at is refused with the current value")
        if profile == "strict":
            check(
                change.get("status") == "pending_review", "strict: field change is held for review"
            )
        else:
            check(change.get("status") == "applied", f"{profile}: field change applied and logged")

        sql = client.call_tool("query_sql", {"sql": "SELECT count(*) AS n FROM uc_notes"})
        check(
            sql.get("ok") if profile == "open" else (sql.get("error") == "disabled"),
            "query_sql is on under open only",
        )

    ok, message, count = verify(audit_path)
    check(ok, f"audit chain: {message}")
    outcomes = [r["outcome"] for r in AuditLog(audit_path).entries()]
    check(count == len(outcomes) and count >= 6, f"one audit row per call ({count})")
    check(map_path.exists() == masking, "session map on disk under masking only")

    if profile == "strict":
        print(
            "  note: the held change stays in the queue; see 'python -m ucs.uc03_mcp_privacy.review list'"
        )
    print()
    if check.failures:
        print(f"FAILED {len(check.failures)} check(s): " + "; ".join(check.failures))
        return 1
    print("OK: every check passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: choose the profile and the database, then run the smoke."""
    parser = argparse.ArgumentParser(
        description="UC-03 demo smoke against a scratch copy of the CRM"
    )
    parser.add_argument(
        "--security", choices=config.SECURITY_PROFILES, default=config.DEFAULT_SECURITY
    )
    parser.add_argument("--db", default=None, help="use this database instead of a scratch copy")
    args = parser.parse_args(argv)

    runtime = config.RUNTIME_DIR / "demo"
    if args.db:
        db = Path(args.db).expanduser().resolve()
    else:
        source = config.db_path()
        if not source.exists():
            print(
                f"CRM database not found: {source} (build it with substrate.pipeline.build_all)",
                file=sys.stderr,
            )
            return 2
        runtime.mkdir(parents=True, exist_ok=True)
        db = runtime / "scratch.db"
        shutil.copyfile(source, db)
    return run(args.security, db, runtime)


if __name__ == "__main__":
    sys.exit(main())
