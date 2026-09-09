"""JSON snapshot persistence for synthetic contacts.

The snapshot is the reproducible artifact; the DB is rebuilt from it.
Private keys (prefixed with '_') are stripped before writing since they are
internal generator state not stored in the DB.

Exception: ``_company_name`` is promoted to the public key ``company_name`` so
that ``build_substrate_db.py`` can resolve the company FK against the
companies snapshot when loading from disk. Contacts with no company
affiliation get ``company_name: null``. This key is intentionally absent from
the Contact SQLModel: it is a snapshot-only resolution hint, not a DB column.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from utils.file_safety import require_can_write
from utils.paths import CONTACTS_SNAPSHOT


def _strip_private(c: dict) -> dict:
    """Drop ``_``-prefixed internal keys; promote ``_company_name`` to ``company_name``."""
    out = {k: v for k, v in c.items() if not k.startswith("_")}
    out["company_name"] = c.get("_company_name")
    return out


def _json_default(obj: object) -> str:
    """Serialise non-JSON-native values (datetime.date) to ISO strings."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def save_snapshot(
    contacts: list[dict],
    path: Path | str = CONTACTS_SNAPSHOT,
    *,
    overwrite: bool = False,
) -> None:
    """Write the generated contact list to a JSON snapshot file.

    The snapshot is the reproducible artifact; the DB is rebuilt from it.
    Internal generator keys (``_``-prefixed) are stripped before writing.
    """
    path = require_can_write(path, overwrite=overwrite, artifact="contact snapshot")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [_strip_private(c) for c in contacts],
            f,
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
