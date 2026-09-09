"""UC-03 routes: the MCP chat with the UC-02 envelope at the boundary, as the page drives it.

One chat window is one session: the model host keeps the conversation under the
native conversation ID (``chat.run_turn(resume=...)``) and the envelope map of the session
folder is shared across the turns. A session is issued by ``POST /uc03/session`` with a
fixed profile, provider, model and tier; turns are serialized by a per-session lock.
The chat route accepts ``claude``, ``codex`` and ``agy`` MCP hosts; unsupported
providers are rejected without a fallback. Dictation goes through
``stt.transcribe_pcm`` (local Whisper by default). Everything a chat writes lands in a
scratch copy of the substrate, never in the record database.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import jobs
from common import (
    RUNTIME_DIR,
    UPLOADS_DIR,
    provider_http_error,
    read_json,
    read_text,
    require_llm_calls_on,
)
from ucs.uc03_mcp_privacy import config as uc03_config
from ucs.uc03_mcp_privacy import stt
from ucs.uc03_mcp_privacy.audit_log import verify as verify_audit
from ucs.uc03_mcp_privacy.chat import MCP_PROVIDERS, run_turn, session_dir
from ucs.uc03_mcp_privacy.envelope import EnvelopeUnavailable
from ucs.uc03_mcp_privacy.tools import TOOL_NAMES, CrmTools
from utils.paths import SUBSTRATE_DB, UC03_DIR
from utils.generation import DEFAULT_MODELS

router = APIRouter()

_MANIFEST = UC03_DIR / "tool_manifest.json"
# The page's chats write notes and field changes; they land in this copy of the
# substrate, never in the record database the runs of UC-01 and UC-04 are hashed on.
_SCRATCH_DB = RUNTIME_DIR / "uc03-substrate.db"
_EVAL_DIR = UC03_DIR / "eval"

_INFRA_TOOLS = {"ping", "server_info", "whoami"}
_WRITE_TOOLS = {"create_note", "update_note", "delete_note", "update_contact", "update_company"}
_DISABLED_UNDER = {"query_sql": ("masked", "strict")}
_HELD_UNDER_STRICT = {"update_contact", "update_company"}


# ---------------------------------------------------------------------------
# Request shapes
# ---------------------------------------------------------------------------


class SessionRequest(BaseModel):
    """Open a chat session under a security profile with one model."""

    profile: str = "strict"
    provider: str = "claude"
    model: str | None = None
    tier: str | None = None


class ChatRequest(BaseModel):
    """One user turn of an issued session; ``profile`` may only repeat the session's."""

    session: str
    message: str
    profile: str | None = None
    provider: str = "claude"
    model: str | None = None
    tier: str | None = None


# ---------------------------------------------------------------------------
# Sessions: issued here, serialized per session
# ---------------------------------------------------------------------------


class _Session:
    """What the bridge remembers about one chat window: profile, model, turns, its lock."""

    def __init__(
        self,
        session: str,
        profile: str,
        model: str,
        provider: str = "claude",
        tier: str | None = None,
    ) -> None:
        """Record a freshly issued session's profile, model choice and per-session turn lock."""
        self.session = session
        self.profile = profile
        self.model = model
        self.provider = provider
        self.tier = tier
        self.turns = 0
        self.created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.lock = asyncio.Lock()

    def to_dict(self) -> dict[str, Any]:
        """A snapshot for the page: profile, model, turn count and whether a turn is running."""
        return {
            "session": self.session,
            "profile": self.profile,
            "model": self.model,
            "provider": self.provider,
            "tier": self.tier,
            "turns": self.turns,
            "created": self.created,
            "busy": self.lock.locked(),
        }


_SESSIONS: dict[str, _Session] = {}


def _profile(value: str | None) -> str:
    """Validate and normalize a security profile name; 400 if it is not one of the known ones."""
    try:
        return uc03_config.security_profile(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown_profile: {exc}") from exc


def _session(session: str) -> _Session:
    """The session record by id; 404 if no session was opened under that id."""
    record = _SESSIONS.get(session)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"session_not_found: {session}; open one with POST /uc03/session",
        )
    return record


# ---------------------------------------------------------------------------
# The scratch database
# ---------------------------------------------------------------------------


def scratch_db(reset: bool = False) -> Path:
    """The copy of ``substrate.db`` the page's chats write into; made on first use."""
    if not SUBSTRATE_DB.exists():
        raise HTTPException(status_code=503, detail=f"substrate_missing: {SUBSTRATE_DB}")
    if reset or not _SCRATCH_DB.exists():
        _SCRATCH_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SUBSTRATE_DB, _SCRATCH_DB)
    return _SCRATCH_DB


@router.post("/uc03/reset-db")
def uc03_reset_db() -> dict[str, Any]:
    """Replace the scratch copy with a fresh copy of the record database; forgets the sessions.

    Refused while a turn is in flight: the server of that turn holds the old file open.
    """
    if any(s.lock.locked() for s in _SESSIONS.values()):
        raise HTTPException(status_code=409, detail="turn_in_flight: počkejte na odpověď modelu.")
    path = scratch_db(reset=True)
    _SESSIONS.clear()
    return {"db": str(path), "reset": True}


# ---------------------------------------------------------------------------
# Turns
# ---------------------------------------------------------------------------


@router.post("/uc03/session")
def uc03_session(req: SessionRequest) -> dict[str, Any]:
    """Open a session: a UUID the model host and the envelope share across the turns."""
    if req.provider not in MCP_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported_mcp_provider: {req.provider}; supported: {', '.join(MCP_PROVIDERS)}",
        )
    import importlib

    adapter = importlib.import_module(f"utils.generation.{req.provider}")
    try:
        model = adapter.normalize_model(req.model or DEFAULT_MODELS[req.provider])
        tier = (
            adapter.normalize_tier(req.tier, model)
            if req.provider in ("codex", "agy")
            else adapter.normalize_tier(req.tier)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = _Session(str(uuid.uuid4()), _profile(req.profile), model, req.provider, tier)
    _SESSIONS[record.session] = record
    return record.to_dict()


@router.get("/uc03/session/{session}")
def uc03_session_get(session: str) -> dict[str, Any]:
    """The session record (profile, model, turns so far, whether a turn is in flight)."""
    return _session(session).to_dict()


@router.post("/uc03/chat")
async def uc03_chat(req: ChatRequest) -> dict[str, Any]:
    """One turn: mask the request, let the model host call the server's tools, restore the answer."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")
    if req.provider not in MCP_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported_mcp_provider: {req.provider!r}; supported: {', '.join(MCP_PROVIDERS)}"
            ),
        )
    require_llm_calls_on(req.provider)
    jobs.require_no_maintenance()
    record = _session(req.session)
    if req.provider != record.provider or req.tier != record.tier:
        raise HTTPException(
            status_code=400,
            detail="generation_fixed: provider and effort are fixed for this session; open a new session.",
        )
    if req.profile and _profile(req.profile) != record.profile:
        raise HTTPException(
            status_code=400,
            detail=f"profile_fixed: session runs under {record.profile}; open a new session to change it.",
        )
    import importlib

    adapter = importlib.import_module(f"utils.generation.{record.provider}")
    try:
        requested_model = adapter.normalize_model(req.model) if req.model else record.model
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if requested_model != record.model:
        raise HTTPException(
            status_code=400,
            detail=f"model_fixed: session runs on {record.model}; open a new session to change it.",
        )
    if record.lock.locked():
        raise HTTPException(status_code=409, detail="turn_in_flight: počkejte na odpověď modelu.")

    async with record.lock:
        audit_path = session_dir(record.session) / "audit.jsonl"
        audit_before = len(_audit_entries(audit_path))
        resume = record.turns > 0
        started = time.perf_counter()
        try:
            report = await run_turn(
                message,
                session=record.session,
                profile=record.profile,
                model=record.model,
                provider=record.provider,
                tier=record.tier,
                db=str(scratch_db()),
                timeout=240,
                resume=resume,
            )
        except EnvelopeUnavailable as exc:  # fail closed: nothing goes to the model
            raise HTTPException(
                status_code=503, detail=f"pseudonymizace nedostupná: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise provider_http_error(exc, prefix="uc03_chat_failed") from exc
        record.turns += 1
        # The CLI's JSON envelope carries no transcript in current versions, so the wrapper
        # often sees no tool calls; the audit chain saw every one of them, and under the
        # session lock the rows added during this turn are exactly this turn's calls.
        tool_calls = report["tool_calls"] or [
            {
                "tool": e.get("tool"),
                "input": {},
                "output": None,
                "args_hash": e.get("args_hash"),
                "from_audit": True,
            }
            for e in _audit_entries(audit_path)[audit_before:]
        ]
        latency_ms = int((time.perf_counter() - started) * 1000)

    return {
        "session": record.session,
        "turn": record.turns,
        "resumed": resume,
        "profile": report["profile"],
        "model": record.model,
        "provider": record.provider,
        "tier": record.tier,
        "restoration": report.get("restoration", {"ok": True}),
        "answer": report["answer"] or "(prázdná odpověď)",
        "you_said": report["you_said"],
        "model_saw": report["model_saw"],
        "answer_model_view": report["answer_model_view"],
        "tool_calls": tool_calls,
        "audit": report.get("audit", {}),
        "session_map": report.get("session_map"),
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# Audit, tools, review queue
# ---------------------------------------------------------------------------


def _audit_entries(path: Path) -> list[dict[str, Any]]:
    """Every row of one audit log (an empty list before the first call)."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


@router.get("/uc03/audit")
def uc03_audit(session: str, limit: int = 30) -> dict[str, Any]:
    """The tail of the session's hash-chained audit log and the chain verification."""
    limit = max(1, min(limit, 200))
    try:
        uuid.UUID(session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session must be a UUID") from exc
    path = session_dir(session) / "audit.jsonl"
    if not path.exists():
        return {"entries": [], "total": 0, "verify": {"ok": True, "message": "no calls yet"}}
    all_entries = _audit_entries(path)
    ok, message, count = verify_audit(path)
    return {
        "entries": all_entries[-limit:],
        "total": len(all_entries),
        "verify": {"ok": ok, "message": message, "entries": count},
        "path": str(path),
    }


@router.get("/uc03/tools")
def uc03_tools(profile: str = "strict") -> dict[str, Any]:
    """The server's tools from the committed manifest pin, with what the profile does to them."""
    profile = _profile(profile)
    manifest = read_json(_MANIFEST, {}) or {}
    pinned = manifest.get("tools", {})
    tools = []
    for name in TOOL_NAMES:
        payload = (pinned.get(name) or {}).get("payload", {})
        description = str(payload.get("description") or "").strip()
        first_paragraph = description.split("\n\n", 1)[0].replace("\n", " ").strip()
        params = list((payload.get("inputSchema") or {}).get("properties", {}).keys())
        kind = "infra" if name in _INFRA_TOOLS else "write" if name in _WRITE_TOOLS else "read"
        tools.append(
            {
                "name": name,
                "kind": kind,
                "description": first_paragraph,
                "description_full": description,
                "params": params,
                "disabled": profile in _DISABLED_UNDER.get(name, ()),
                "held_for_review": profile == "strict" and name in _HELD_UNDER_STRICT,
                "pinned": name in pinned,
            }
        )
    return {
        "profile": profile,
        "profiles": list(uc03_config.SECURITY_PROFILES),
        "providers": list(MCP_PROVIDERS),
        "tools": tools,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "pinned_at": manifest.get("pinned_at"),
    }


@router.get("/uc03/review")
def uc03_review() -> dict[str, Any]:
    """The field changes held under ``strict`` in the scratch database (the human side, in clear)."""
    try:
        rows = CrmTools(profile="open", db_path=str(scratch_db()), author="human").pending_changes()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"review_queue_unavailable: {exc}") from exc
    return {"changes": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Dictation
# ---------------------------------------------------------------------------


@router.post("/uc03/transcribe")
async def uc03_transcribe(
    file: UploadFile = File(...),
    backend: str = Form(uc03_config.DEFAULT_STT_BACKEND),
    model_size: str = Form(uc03_config.WHISPER_MODEL),
) -> dict[str, Any]:
    """Transcribe one WAV recording (16 kHz mono 16-bit) with the chosen speech backend.

    Local Whisper needs no switch; the Google backends are paid and switch-gated.
    """
    if backend not in uc03_config.STT_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown_stt_backend: {backend}; known: {', '.join(uc03_config.STT_BACKENDS)}",
        )
    if backend != "whisper":
        require_llm_calls_on()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADS_DIR / f"{uuid.uuid4().hex}.wav"
    target.write_bytes(await file.read())
    started = time.perf_counter()
    try:
        pcm = stt.read_wav_pcm(target)
        text = stt.transcribe_pcm(pcm, backend=backend, model_size=model_size)
    except ValueError as exc:  # not the WAV format the pipeline expects
        raise HTTPException(status_code=400, detail=f"bad_wav: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"transcription_failed: {exc}") from exc
    finally:
        target.unlink(missing_ok=True)
    return {
        "text": text,
        "backend": backend,
        "model": model_size if backend == "whisper" else None,
        "seconds": round(time.perf_counter() - started, 1),
        "audio_seconds": round(
            len(pcm) / (uc03_config.SAMPLE_RATE * uc03_config.SAMPLE_WIDTH_BYTES), 1
        ),
    }


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@router.get("/uc03/results")
def uc03_results() -> dict[str, Any]:
    """The Whisper evaluation on the synthetic corpus: the two summaries and the eval README."""
    synth = _EVAL_DIR / "synth"
    summaries = {
        path.stem.replace("summary_", ""): read_json(path, {})
        for path in sorted(synth.glob("summary_*.json"))
    }
    return {
        "summaries": summaries,
        "readme": read_text(_EVAL_DIR / "README.md"),
        "whisper_model_default": uc03_config.WHISPER_MODEL,
        "stt_backends": list(uc03_config.STT_BACKENDS),
        "source": str(synth),
    }


def runtime_paths() -> dict[str, Any]:
    """Where the sessions and the scratch database of this bridge live (for ``/health``)."""
    return {
        "sessions_dir": str(Path(uc03_config.RUNTIME_DIR) / "sessions"),
        "scratch_db": str(_SCRATCH_DB),
        "scratch_db_exists": _SCRATCH_DB.exists(),
    }
