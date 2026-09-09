"""UC-02 routes: the reversible pseudonymizer as the page drives it.

``mask`` and ``restore`` are ``pseudonymize`` / ``depseudonymize`` of the UC-02 code;
``roundtrip`` is the envelope of the live check (mask, one model call, integrity check,
restore) through ``with_envelope``. The results routes read the run folders and the cards
under ``eval/``.
"""

from __future__ import annotations

import csv
import random
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import jobs
from common import (
    ModelChoice,
    check_provider,
    provider_http_error,
    read_json,
    read_text,
    require_llm_calls_on,
    run_folders,
)
from ucs.uc02_pseudonymization.code.envelope import (
    EnvelopeIntegrityError,
    EnvelopeProviderError,
    compose_system_prompt,
    make_detector,
    mask as envelope_mask,
    with_envelope,
)
from ucs.uc02_pseudonymization.code.ner import (
    CANDIDATE_MODELS,
    DEFAULT_NER_BACKEND,
    LICENCES,
    MODEL_IDS,
    NER_BACKENDS,
)
from ucs.uc02_pseudonymization.code.pseudonymizer import depseudonymize, pseudonymize
from ucs.uc02_pseudonymization.eval import runs as uc02_runs
from ucs.uc02_pseudonymization.eval.live_check import TASKS
from utils.generation import generate_text
from utils.paths import UC02_DIR, UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT

router = APIRouter()

_EVAL_DIR = UC02_DIR / "eval"
_RUNS_DIR = _EVAL_DIR / "runs"
_ROUNDTRIP_SEED = 20260907  # the token numbers of a roundtrip are reproducible


# ---------------------------------------------------------------------------
# Request and response shapes
# ---------------------------------------------------------------------------


class MaskRequest(BaseModel):
    """One text to pseudonymize; NER on unless switched off."""

    text: str
    use_ner: bool = True
    ner_backend: str | None = None


class RestoreRequest(BaseModel):
    """Restore a masked (or model-rewritten) text from the mapping ``mask`` returned."""

    text: str
    mapping: list[dict[str, Any]]
    original: str | None = None


class RoundtripRequest(ModelChoice):
    """Mask, send through a model, restore: the sandwich of the live check."""

    text: str
    use_ner: bool = True
    ner_backend: str | None = None
    task: str = "summarize"


# ---------------------------------------------------------------------------
# Mask and restore
# ---------------------------------------------------------------------------


@router.post("/uc02/mask")
def uc02_mask(req: MaskRequest) -> dict[str, Any]:
    """Pseudonymize one message through the UC-02 code; the mapping stays with the caller."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    if req.ner_backend and req.ner_backend not in NER_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown_ner_backend: {req.ner_backend}; known: {', '.join(NER_BACKENDS)}",
        )
    started = time.perf_counter()
    try:
        masked, mapping = pseudonymize(text, use_ner=req.use_ner, ner_backend=req.ner_backend)
    except RuntimeError as exc:  # the NER layer could not run: fail closed, say why
        raise HTTPException(status_code=503, detail=f"ner_unavailable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surface failures directly
        raise HTTPException(status_code=502, detail=f"uc02_mask_failed: {exc}") from exc
    counts: dict[str, int] = {}
    for row in mapping:
        counts[str(row["pii_type"])] = counts.get(str(row["pii_type"]), 0) + 1
    return {
        "masked": masked,
        "mapping": mapping,
        "counts": counts,
        "use_ner": req.use_ner,
        "ner_backend": (req.ner_backend or DEFAULT_NER_BACKEND) if req.use_ner else None,
        "seconds": round(time.perf_counter() - started, 2),
        "backend": "ucs.uc02_pseudonymization.code.pseudonymizer.pseudonymize",
    }


@router.post("/uc02/restore")
def uc02_restore(req: RestoreRequest) -> dict[str, Any]:
    """Put the values back; ``exact`` compares with the original when the page sends it."""
    try:
        restored = depseudonymize(req.text, req.mapping)
    except Exception as exc:  # noqa: BLE001 - surface failures directly
        raise HTTPException(status_code=502, detail=f"uc02_restore_failed: {exc}") from exc
    return {
        "restored": restored,
        "exact": (restored == req.original) if req.original is not None else None,
        "backend": "ucs.uc02_pseudonymization.code.pseudonymizer.depseudonymize",
    }


# ---------------------------------------------------------------------------
# The sandwich with a real model
# ---------------------------------------------------------------------------


@router.post("/uc02/roundtrip")
async def uc02_roundtrip(req: RoundtripRequest) -> dict[str, Any]:
    """Mask the text, let a model work on the masked version, restore the answer.

    The same envelope as the live check: random token numbers, the id line the model
    must echo, the integrity check with one reminder per failure, then the restore.
    The token numbers are drawn from a fixed seed so the page can show the masked text
    that went out (``mask`` with the same seed gives the same tokens).
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    if req.task not in TASKS:
        raise HTTPException(
            status_code=400, detail=f"unknown_task: {req.task}; known: {list(TASKS)}"
        )
    check_provider(req.provider)
    require_llm_calls_on(req.provider)
    jobs.require_no_maintenance()

    if req.ner_backend and req.ner_backend not in NER_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown_ner_backend: {req.ner_backend}; known: {', '.join(NER_BACKENDS)}",
        )
    detector = make_detector(req.use_ner, req.ner_backend)
    system_prompt = compose_system_prompt(
        TASKS[req.task], detection="rules+ner" if req.use_ner else "rules"
    )
    attempts: list[dict[str, Any]] = []

    async def llm_call(prompt: str) -> str:
        """Send the masked prompt to the selected model under the chosen provider/tier."""
        return await generate_text(
            prompt,
            provider=req.provider,
            system_prompt=system_prompt,
            model=req.model,
            tier=req.tier,
            timeout=180,
        )

    started = time.perf_counter()
    try:
        masked, mapping = envelope_mask(
            text, detector=detector, unify="entity", rng=random.Random(_ROUNDTRIP_SEED)
        )
        restored = await with_envelope(
            text,
            llm_call,
            detector=detector,
            unify="entity",
            rng=random.Random(_ROUNDTRIP_SEED),
            timeout_per_attempt=180,
            on_attempt=attempts.append,
        )
    except RuntimeError as exc:
        if isinstance(exc, (EnvelopeIntegrityError, EnvelopeProviderError)):
            raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc
        raise HTTPException(status_code=503, detail=f"ner_unavailable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise provider_http_error(exc, prefix="uc02_roundtrip_failed") from exc

    last = next((a for a in reversed(attempts) if "response" in a), None)
    return {
        "masked": masked,
        "mapping": [
            {"token": token, "surface_form": value, "pii_type": token.strip("<>").rsplit("_", 1)[0]}
            for token, value in mapping.entries.items()
        ],
        "system_prompt": system_prompt,
        "attempts": [
            {
                "attempt": a.get("attempt"),
                "prompt": a.get("prompt"),
                "response": a.get("response"),
                "mid_ok": a.get("mid_ok"),
                "integrity_ok": a.get("integrity_ok"),
                "missing": sorted(a.get("missing", []) or []),
                "extra": sorted(a.get("extra", []) or []),
                "passthrough": a.get("passthrough", False),
                "error": a.get("error"),
            }
            for a in attempts
        ],
        "model_answer_masked": last.get("response")
        if last
        else (restored if any(a.get("passthrough") for a in attempts) else None),
        "restored": restored,
        "provider": req.provider,
        "model": req.model,
        "tier": req.tier,
        "task": req.task,
        "use_ner": req.use_ner,
        "ner_backend": (req.ner_backend or DEFAULT_NER_BACKEND) if req.use_ner else None,
        "seconds": round(time.perf_counter() - started, 1),
        "backend": "ucs.uc02_pseudonymization.code.envelope.with_envelope + utils.generation",
    }


# ---------------------------------------------------------------------------
# Samples and results
# ---------------------------------------------------------------------------


@router.get("/uc02/samples")
def uc02_samples(limit: int = 12) -> dict[str, Any]:
    """Rows of the UC-02 corpus of record for the sample picker."""
    limit = max(1, min(limit, 100))
    rows = read_json(UC02_PII_CORPUS_SNAPSHOT, [])
    samples = [
        {
            "id": row["message_id"],
            "label": f"{row['channel']} · {row['density_band']} · {row['planted_pii_count']} PII",
            "text": row["text"],
            "scenario": row.get("scenario"),
            "channel": row.get("channel"),
            "density_band": row.get("density_band"),
            "planted_pii_count": row.get("planted_pii_count"),
        }
        for row in rows[:limit]
    ]
    return {"samples": samples, "source": str(UC02_PII_CORPUS_SNAPSHOT)}


@router.get("/uc02/results")
def uc02_results() -> dict[str, Any]:
    """The results card, the NER comparison and the run folders under ``eval/runs/``."""
    runs = []
    for folder in run_folders(_RUNS_DIR):
        config = read_json(folder / "config.json", {}) or {}
        runs.append(
            {
                "name": folder.name,
                "has_card": (folder / "RESULTS.md").exists(),
                "date": config.get("date") or config.get("created"),
                "kind": _uc02_kind(folder.name),
                "configs": len(config.get("configs", []) or []) or None,
            }
        )
    return {
        "card": read_text(_EVAL_DIR / "RESULTS.md"),
        "ner_comparison": read_text(_EVAL_DIR / "NER-COMPARISON.md"),
        "runs": runs,
        "source": str(_EVAL_DIR),
    }


@router.get("/uc02/runs/{name}")
def uc02_run(name: str) -> dict[str, Any]:
    """The card and the table of one UC-02 run folder."""
    from common import folder_or_404

    folder = folder_or_404(_RUNS_DIR, name)
    return {
        "name": folder.name,
        "card": read_text(folder / "RESULTS.md"),
        "table": read_text(folder / "TABLE.md"),
        "summary": read_json(folder / "summary.json", None),
    }


def _uc02_kind(name: str) -> str:
    """Classify a run folder name by the substring it contains (detection, sandwich, ...)."""
    for key, kind in (
        ("detection-table", "detection"),
        ("false-alarms", "false-alarms"),
        ("sandwich", "sandwich"),
        ("candidate", "smoke"),
    ):
        if key in name:
            return kind
    return "other"


# ---------------------------------------------------------------------------
# The NER backends the page can choose from
# ---------------------------------------------------------------------------


def _newest_run(kind: str, *, on_record_corpus: bool = False) -> Path | None:
    """The newest run folder whose ``config.json`` says ``kind``; optionally only runs on
    the corpus of record as it is now (same corpus id as the snapshot)."""
    wanted = None
    if on_record_corpus:
        wanted = uc02_runs.corpus_identity(UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT).get(
            "corpus_id"
        )
    for folder in run_folders(_RUNS_DIR):
        config = read_json(folder / "config.json", {}) or {}
        if config.get("kind") != kind:
            continue
        if wanted and (config.get("corpus") or {}).get("corpus_id") != wanted:
            continue
        return folder
    return None


def _f1_by_backend(run_dir: Path | None, casing: str | None) -> dict[str, float]:
    """Strict F1 of every ``rules+<backend>`` row of a run's ``overall.csv``."""
    out: dict[str, float] = {}
    if run_dir is None or not (run_dir / "overall.csv").exists():
        return out
    with (run_dir / "overall.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if casing is not None and row.get("casing") != casing:
                continue
            cfg = row.get("config", "")
            if cfg.startswith("rules+"):
                out[cfg[len("rules+") :]] = float(row["f1"])
    return out


@router.get("/uc02/ner-backends")
def uc02_ner_backends() -> dict[str, Any]:
    """Every NER backend the package knows, with the record table's strict F1 (rules + NER)
    and, when a casing table exists, the F1 on the same corpus written in lower case."""
    record = _newest_run("detection-table", on_record_corpus=True)
    casing = _newest_run("casing-table", on_record_corpus=True)
    f1 = _f1_by_backend(record, None)
    lower = _f1_by_backend(casing, "lower")
    return {
        "backends": [
            {
                "backend": backend,
                "default": backend == DEFAULT_NER_BACKEND,
                "licence": LICENCES.get(backend),
                "model": MODEL_IDS.get(backend),
                "note": (CANDIDATE_MODELS.get(backend) or {}).get("note"),
                "f1": f1.get(backend),
                "f1_lower": lower.get(backend),
            }
            for backend in NER_BACKENDS
        ],
        "default": DEFAULT_NER_BACKEND,
        "record_run": record.name if record else None,
        "casing_run": casing.name if casing else None,
    }
