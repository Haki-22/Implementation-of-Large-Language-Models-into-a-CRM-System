"""Review queue: the human step for field changes the model requested under ``strict``.

Under the strict security profile ``update_contact`` and ``update_company``
record the change in ``uc_change_log`` and stop. A person looks at the queue
in clear (this runs on the machine that holds the database, nothing here goes
through a model) and applies or rejects each change. The outcome and the time
are written back to the row, so the log stays a complete record of what the
model asked for and what a person decided.

CLI
---
    python -m ucs.uc03_mcp_privacy.review list
    python -m ucs.uc03_mcp_privacy.review apply <change_id>
    python -m ucs.uc03_mcp_privacy.review reject <change_id>
    python -m ucs.uc03_mcp_privacy.review apply-all
"""

from __future__ import annotations

import argparse
import json
import sys

from ucs.uc03_mcp_privacy.tools import CrmTools


def _tools(db: str | None) -> CrmTools:
    """Return the `CrmTools` this CLI reviews with: open profile, human author, no envelope.

    The queue is read and decided by a person on the local machine.
    """
    return CrmTools(profile="open", db_path=db, author="human")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: list, apply or reject held changes."""
    parser = argparse.ArgumentParser(description="UC-03 review queue for held field changes")
    parser.add_argument(
        "--db", default=None, help="CRM SQLite path (default: UC03_DB_PATH / substrate)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show the held changes")
    for name in ("apply", "reject"):
        p = sub.add_parser(name, help=f"{name} one held change")
        p.add_argument("change_id", type=int)
    sub.add_parser("apply-all", help="apply every held change")
    args = parser.parse_args(argv)

    tools = _tools(args.db)
    if args.cmd == "list":
        rows = tools.pending_changes()
        if not rows:
            print("no held changes")
            return 0
        for row in rows:
            state = (
                "still current" if row["still_current"] else f"MOVED, now {row['current_value']!r}"
            )
            print(
                f"#{row['id']:<4} {row['entity_type']:<8} id={row['entity_id']:<5} "
                f"{row['field']:<16} {row['old_value']!r} -> {row['new_value']!r}   "
                f"by {row['author']} at {row['created_at']} (audit seq {row['audit_seq']}); {state}"
            )
        return 0
    if args.cmd == "apply-all":
        for row in tools.pending_changes():
            print(json.dumps(tools.review_change(row["id"], "applied")))
        return 0
    outcome = "applied" if args.cmd == "apply" else "rejected"
    result = tools.review_change(args.change_id, outcome)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
