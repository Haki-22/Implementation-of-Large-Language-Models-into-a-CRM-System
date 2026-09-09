"""Helpers every route module of the bridge shares: paths, the model-call gate,
error mapping, the database connection, run-folder listing and the model choice
a page request carries.

Nothing here calls a model or runs a use case; the route modules do that through
the same plain functions the CLIs call.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from utils.generation import DEFAULT_PROVIDER, DEFAULT_TIER, PROVIDERS
from utils.generation.errors import GenerationError, LLMCallsDisabledError
from utils.llm_switch import llm_calls_enabled
from utils.paths import SUBSTRATE_DB

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BRIDGE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BRIDGE_DIR / ".runtime"
# Runs started from the page refresh their appendix files here, never under
# attachments/: the page can never rewrite the thesis appendix.
PAGE_ATTACHMENTS_DIR = RUNTIME_DIR / "attachments"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
# The page history: the thread and the last choices of every tab, one JSON file per tab
# (see routes_history.py); deleted from the settings screen, never a run of record.
HISTORY_DIR = RUNTIME_DIR / "history"


def ensure_runtime_dirs() -> None:
    """Create the runtime folders the routes write into."""
    for path in (RUNTIME_DIR, PAGE_ATTACHMENTS_DIR, UPLOADS_DIR, HISTORY_DIR):
        path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# The model-call gate and provider errors
# ---------------------------------------------------------------------------


class ModelChoice(BaseModel):
    """The provider, model and tier a page request carries (the page's settings)."""

    provider: str = DEFAULT_PROVIDER
    model: str | None = None
    tier: str | None = DEFAULT_TIER


def check_provider(provider: str) -> str:
    """400 for a provider name the generation layer does not know."""
    if provider not in PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown_provider: {provider!r}; known: {', '.join(PROVIDERS)}",
        )
    return provider


def require_llm_calls_on(provider: str | None = None) -> None:
    """Fail closed (HTTP 403) when the process-wide model-call switch is off.

    The mock provider never calls anything and passes regardless.
    """
    if provider == "mock":
        return
    if not llm_calls_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "llm_calls_off: volání modelů jsou vypnutá. Zapněte je v Nastavení "
                "(přepínač LLM) nebo nastavte THESIS_LLM_CALLS=TRUE v .env."
            ),
        )


def provider_http_error(exc: Exception, *, prefix: str) -> HTTPException:
    """Map a provider or runtime failure onto an HTTP error the page can show."""
    if isinstance(exc, LLMCallsDisabledError):
        return HTTPException(status_code=403, detail=f"llm_calls_off: {exc}")
    if isinstance(exc, GenerationError):
        hint = f" ({exc.hint})" if getattr(exc, "hint", None) else ""
        return HTTPException(status_code=502, detail=f"{exc.provider} selhal: {exc.message}{hint}")
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(status_code=502, detail=f"{prefix}: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Files and run folders
# ---------------------------------------------------------------------------


def read_text(path: Path) -> str:
    """The file's text, or an empty string when it does not exist."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path, fallback: Any = None) -> Any:
    """The parsed JSON file, or ``fallback`` when it is missing or unreadable."""
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def run_folders(base: Path) -> list[Path]:
    """Run folders under ``base`` (those with a ``config.json``), newest name first."""
    if not base.exists():
        return []
    return sorted(
        (p for p in base.iterdir() if p.is_dir() and (p / "config.json").exists()),
        key=lambda p: p.name,
        reverse=True,
    )


def folder_or_404(base: Path, name: str) -> Path:
    """The run folder ``name`` under ``base``; 404 when absent or outside ``base``."""
    if not name or "/" in name or name.startswith("."):
        raise HTTPException(status_code=404, detail=f"run_not_found: {name}")
    folder = base / name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"run_not_found: {name}")
    return folder


# ---------------------------------------------------------------------------
# The substrate database (read-only)
# ---------------------------------------------------------------------------


def connect_db() -> sqlite3.Connection:
    """Open ``substrate.db`` with dict-like rows; 503 when it has not been built."""
    if not SUBSTRATE_DB.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"substrate_missing: {SUBSTRATE_DB} — run "
                "`python -m substrate.pipeline.build_all --verify` first."
            ),
        )
    conn = sqlite3.connect(f"file:{SUBSTRATE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """One read-only query as plain dictionaries."""
    with connect_db() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def db_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """One read-only query, first row or ``None``."""
    rows = db_rows(sql, params)
    return rows[0] if rows else None
