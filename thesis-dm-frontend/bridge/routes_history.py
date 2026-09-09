"""The page history: the thread and the last choices of every tab, kept in the bridge's
runtime folder so a tab switch or a reload does not lose them.

One JSON file per tab under ``.runtime/history/`` with ``{"thread": [...], "state": {...},
"updated": ...}``. The page writes the whole file after every change (write-behind, a few
hundred milliseconds after the last edit) and reads it when the tab opens; the settings
screen lists the files and deletes them. Nothing here is a run of record: the folder is
gitignored with the rest of ``.runtime/``, and a thread the page kept has no bearing on the
run folders the use cases write.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from common import HISTORY_DIR

router = APIRouter()

TABS = ("uc01", "uc02", "uc03", "uc04", "code")
MAX_THREAD = 200  # turns kept per tab; the oldest fall off the front
_lock = threading.Lock()


class HistoryBody(BaseModel):
    """What the page holds for one tab: the thread as rendered, the choices as made."""

    thread: list[dict[str, Any]] = []
    state: dict[str, Any] = {}


def _path(tab: str):
    """The history file for ``tab``; 404 if ``tab`` is not one of ``TABS``."""
    if tab not in TABS:
        raise HTTPException(status_code=404, detail=f"unknown_tab: {tab}; known: {', '.join(TABS)}")
    return HISTORY_DIR / f"{tab}.json"


def _read(tab: str) -> dict[str, Any]:
    """Load ``tab``'s history file, falling back to an empty thread/state on error or absence."""
    path = _path(tab)
    empty = {"tab": tab, "thread": [], "state": {}, "updated": None}
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    return {
        "tab": tab,
        "thread": data.get("thread") or [],
        "state": data.get("state") or {},
        "updated": data.get("updated"),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/history")
def history_summary() -> dict[str, Any]:
    """Every tab's file: how many turns, how many bytes, when it was last written."""
    tabs = []
    for tab in TABS:
        path = HISTORY_DIR / f"{tab}.json"
        data = _read(tab)
        tabs.append(
            {
                "tab": tab,
                "messages": len(data["thread"]),
                "bytes": path.stat().st_size if path.exists() else 0,
                "updated": data["updated"],
            }
        )
    return {"dir": str(HISTORY_DIR), "tabs": tabs}


@router.get("/history/{tab}")
def history_read(tab: str) -> dict[str, Any]:
    """The thread and the state of one tab; empty when nothing was kept yet."""
    return _read(tab)


@router.put("/history/{tab}")
def history_write(tab: str, body: HistoryBody) -> dict[str, Any]:
    """Replace the tab's file with what the page holds now (atomic: tmp file + rename)."""
    path = _path(tab)
    thread = body.thread[-MAX_THREAD:]
    payload = {
        "tab": tab,
        "thread": thread,
        "state": body.state,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    text = json.dumps(payload, ensure_ascii=False)
    with _lock:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return {
        "tab": tab,
        "messages": len(thread),
        "bytes": len(text.encode("utf-8")),
        "updated": payload["updated"],
    }


@router.delete("/history/{tab}")
def history_delete(tab: str) -> dict[str, Any]:
    """Remove one tab's file."""
    path = _path(tab)
    with _lock:
        existed = path.exists()
        if existed:
            path.unlink()
    return {"tab": tab, "deleted": existed}


@router.delete("/history")
def history_delete_all() -> dict[str, Any]:
    """Remove every tab's file."""
    deleted = 0
    with _lock:
        for tab in TABS:
            path = HISTORY_DIR / f"{tab}.json"
            if path.exists():
                path.unlink()
                deleted += 1
    return {"deleted": deleted}
