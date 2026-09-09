"""Settings of the UC-03 MCP server, its chat client and the speech-to-text helpers.

Constants only; every value can be overridden through the environment so a test,
the demo smoke or the browser bridge can point the server at its own database,
audit log and session map without touching the code.

Security profiles
------------------------------------
``UC03_SECURITY`` selects how much of chapter 5 the server enforces:

- ``open``   - the full interface: clear values, every column, read-only SQL,
               every write applied at once.
- ``masked`` - ``open`` plus the UC-02 envelope on every tool result and every
               write argument (session tokens, random numbers, fail closed).
- ``strict`` - ``masked`` plus scope: per-tool field allow-lists, no raw SQL,
               contact and company field changes held for a human review.

The audit chain and the tool manifest are on in every profile.
"""

from __future__ import annotations

import os
from pathlib import Path

from utils.paths import SUBSTRATE_DB, UC03_DIR

# ---------------------------------------------------------------------------
# Security profile
# ---------------------------------------------------------------------------

SECURITY_PROFILES: tuple[str, ...] = ("open", "masked", "strict")
DEFAULT_SECURITY = "strict"
ENV_SECURITY = "UC03_SECURITY"


def security_profile(value: str | None = None) -> str:
    """Return the validated profile name: the argument, else the environment, else strict."""
    chosen = (value or os.environ.get(ENV_SECURITY) or DEFAULT_SECURITY).strip().lower()
    if chosen not in SECURITY_PROFILES:
        raise ValueError(f"unknown security profile {chosen!r}; choices: {SECURITY_PROFILES}")
    return chosen


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

RUNTIME_DIR = Path(os.environ.get("UC03_RUNTIME_DIR", str(UC03_DIR / ".runtime"))).expanduser()
"""Where a run leaves its audit log, session map and generated MCP config (gitignored)."""

PIN_PATH = UC03_DIR / "tool_manifest.json"
"""The committed tool manifest pin; ``UC03_MANIFEST_PATH`` overrides it (tests)."""


def db_path() -> Path:
    """The CRM SQLite database the tools read and write (``UC03_DB_PATH`` overrides)."""
    return Path(os.environ.get("UC03_DB_PATH", str(SUBSTRATE_DB))).expanduser()


def audit_path() -> Path:
    """The hash-chained audit log (``UC03_AUDIT_PATH`` overrides)."""
    return Path(os.environ.get("UC03_AUDIT_PATH", str(RUNTIME_DIR / "audit.jsonl"))).expanduser()


def manifest_path() -> Path:
    """The tool manifest pin the server verifies at startup (``UC03_MANIFEST_PATH`` overrides)."""
    return Path(os.environ.get("UC03_MANIFEST_PATH", str(PIN_PATH))).expanduser()


def manifest_strict(profile: str | None = None) -> bool:
    """Fail closed on a manifest mismatch.

    Always under the ``strict`` security profile; under ``open`` and ``masked``
    the development override ``UC03_MANIFEST_STRICT=0`` lets a server start on a
    mismatch.
    """
    if (profile or "").lower() == "strict":
        return True
    return os.environ.get("UC03_MANIFEST_STRICT", "1").strip().lower() not in ("0", "false", "no")


def session_map_path() -> Path:
    """The session envelope file shared by the chat client and the server."""
    return Path(
        os.environ.get("UC03_SESSION_MAP", str(RUNTIME_DIR / "session-map.json"))
    ).expanduser()


def author() -> str:
    """Who is writing through the server: ``human`` or ``llm:<model>`` (``UC03_AUTHOR``)."""
    return os.environ.get("UC03_AUTHOR", "llm").strip() or "llm"


def ensure_runtime_dir() -> Path:
    """Create the runtime directory and return it."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR


# ---------------------------------------------------------------------------
# Speech to text
# ---------------------------------------------------------------------------

STT_BACKENDS: tuple[str, ...] = ("whisper", "google-web", "google-cloud")
DEFAULT_STT_BACKEND = os.environ.get("UC03_STT_BACKEND", "whisper")

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2

MODEL_DIR = Path(os.environ.get("UC03_MODEL_DIR", str(UC03_DIR / "models"))).expanduser()
"""faster-whisper download cache (gitignored, several GB)."""

WHISPER_MODEL = os.environ.get("UC03_WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.environ.get("UC03_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("UC03_WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BEAM_SIZE = int(os.environ.get("UC03_WHISPER_BEAM_SIZE", "5"))
WHISPER_LANGUAGE = os.environ.get("UC03_WHISPER_LANGUAGE", "cs")
WHISPER_VOCAB_FILE = Path(
    os.environ.get("UC03_WHISPER_VOCAB_FILE", str(UC03_DIR / "vocab_cs.txt"))
).expanduser()

GOOGLE_WEB_LANGUAGE = os.environ.get("UC03_GOOGLE_WEB_LANGUAGE", "cs-CZ")
GOOGLE_CLOUD_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
    "GOOGLE_CLOUD_PROJECT_ID", ""
)
GOOGLE_CLOUD_LOCATION = os.environ.get("UC03_GOOGLE_CLOUD_LOCATION", "global")
GOOGLE_CLOUD_RECOGNIZER = os.environ.get("UC03_GOOGLE_CLOUD_RECOGNIZER", "_")
GOOGLE_CLOUD_MODEL = os.environ.get("UC03_GOOGLE_CLOUD_MODEL", "latest_long")
GOOGLE_CLOUD_LANGUAGE = os.environ.get("UC03_GOOGLE_CLOUD_LANGUAGE", "cs-CZ")

RECORD_MAX_SECONDS = float(os.environ.get("UC03_RECORD_MAX_SECONDS", "60"))
"""Upper bound of one push-to-talk recording in the CLI chat."""
