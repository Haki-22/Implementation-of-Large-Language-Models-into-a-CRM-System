"""The installation screen: what a fresh clone still lacks, and the steps that supply it.

A clone ships the code, the committed snapshots and the five large snapshots as
``.json.gz``; it lacks the plain JSON of those five, the database, the two local
models, and (optionally) the raw dumps a full rebuild starts from. ``GET /setup/status``
says which of these is in place; ``POST /setup/run`` runs the chosen steps as one job.
Every step is the documented command or function of the pipeline
(``packing.ensure_unpacked``, ``substrate.pipeline.build_all``, the model loaders),
never a copy of it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import jobs
from substrate.pipeline import packing
from substrate.pipeline.data_acquisition.inputs import download_size_mb, problems, raw_status
from ucs.uc02_pseudonymization.code import ner as uc02_ner
from ucs.uc03_mcp_privacy import config as uc03_config
from utils.generation import cli_status
from utils.paths import SUBSTRATE_DB, THESIS_ROOT

router = APIRouter()

# ---------------------------------------------------------------------------
# The steps and the plans
# ---------------------------------------------------------------------------

STEPS: dict[str, dict[str, Any]] = {
    "unpack": {
        "label": "Rozbalit velké snímky (.json.gz → .json)",
        "detail": "Pět snímků, které git nese komprimované; překlad z 29. 5. 2026 je mezi nimi a znovu se nepřekládá.",
        "command": "python -m substrate.pipeline.packing unpack",
        "cost": "sekundy, bez sítě",
    },
    "database": {
        "label": "Sestavit substrate.db z commitnutých snímků",
        "detail": "Databáze, kterou čtou všechny čtyři use-casy (kontakty, objednávky, recenze s FTS5, výstupy UC-04).",
        "command": "python -m substrate.pipeline.build_all --force --from database",
        "cost": "asi minuta, bez sítě",
    },
    "ner": {
        "label": "Stáhnout NER model pro UC-02 (bardsai, ~1 GB)",
        "detail": "Rozpoznávání jmen, firem a adres v češtině; bez něj běží jen pravidlová vrstva.",
        "command": "první volání pseudonymize(use_ner=True)",
        "cost": "jednou, ~1 GB ze sítě do cache Hugging Face",
    },
    "whisper": {
        "label": "Stáhnout Whisper medium pro UC-03 (~1,5 GB)",
        "detail": "Lokální přepis diktátu; bez něj chat funguje jen psaním.",
        "command": "první volání stt.transcribe_pcm(backend='whisper')",
        "cost": "jednou, ~1,5 GB ze sítě",
    },
    "rebuild": {
        "label": "Úplná rekonstrukce ze surových dumpů",
        "detail": "Stáhne pinované dumpy Amazonu (~680 MB) a ČSÚ + Česká pošta (~885 MB) a přestaví každý snímek; překlad zůstává zmrazený.",
        "command": "python -m substrate.pipeline.build_all --force",
        "cost": "1,5 GB ze sítě, minuty",
    },
}
PLANS: dict[str, tuple[str, ...]] = {
    "minimal": ("unpack", "database", "ner", "whisper"),
    "full": ("unpack", "rebuild", "ner", "whisper"),
}

_NER_MODEL = uc02_ner.PRIMARY_MODEL


class HfTokenRequest(BaseModel):
    """A Hugging Face access token to store for the model downloads (never echoed back)."""

    token: str


class SetupRunRequest(BaseModel):
    """Which steps to run, in this order; ``plan`` names a preset instead."""

    steps: list[str] | None = None
    plan: str | None = None


# ---------------------------------------------------------------------------
# What is in place
# ---------------------------------------------------------------------------


def _hf_cached(model_id: str) -> bool:
    """True if ``model_id`` already has a populated snapshot in the Hugging Face hub cache."""
    from huggingface_hub import constants as hf_constants

    folder = (
        Path(hf_constants.HF_HUB_CACHE) / f"models--{model_id.replace('/', '--')}" / "snapshots"
    )
    return folder.exists() and any(folder.iterdir())


def _hf_token_present() -> bool:
    """True if a Hugging Face access token is stored where the hub client reads it."""
    from huggingface_hub import get_token

    return bool(get_token())


def _whisper_cached(size: str) -> bool:
    """True if the faster-whisper model of ``size`` is already downloaded."""
    folder = Path(uc03_config.MODEL_DIR) / f"models--Systran--faster-whisper-{size}"
    return folder.exists()


def status_payload() -> dict[str, Any]:
    """Every check the installation screen shows, and whether the page can run."""
    packed = packing.status()
    packed_ok = all(state in ("ok", "needs-pack") for state in packed.values())
    db_ok = SUBSTRATE_DB.exists()
    raw = raw_status()
    raw_problems = problems(raw)
    ner_ok = _hf_cached(_NER_MODEL)
    whisper_ok = _whisper_cached(uc03_config.WHISPER_MODEL)
    clis = cli_status()
    checks = [
        {
            "id": "packed",
            "label": "Velké snímky rozbalené",
            "state": "ok" if packed_ok else "todo",
            "detail": {str(Path(p).relative_to(THESIS_ROOT)): s for p, s in packed.items()},
            "step": "unpack",
        },
        {
            "id": "database",
            "label": "Databáze substrate.db",
            "state": "ok" if db_ok else "todo",
            "detail": {
                "path": str(SUBSTRATE_DB.relative_to(THESIS_ROOT)),
                "size_mb": round(SUBSTRATE_DB.stat().st_size / 1e6, 1) if db_ok else None,
            },
            "step": "database",
        },
        {
            "id": "ner_model",
            "label": f"NER model {_NER_MODEL}",
            "state": "ok" if ner_ok else "todo",
            "detail": {"cache": "Hugging Face hub cache"},
            "step": "ner",
        },
        {
            "id": "whisper_model",
            "label": f"Whisper {uc03_config.WHISPER_MODEL} (faster-whisper)",
            "state": "ok" if whisper_ok else "todo",
            "detail": {"dir": str(Path(uc03_config.MODEL_DIR).relative_to(THESIS_ROOT))},
            "step": "whisper",
        },
        {
            "id": "raw_inputs",
            "label": "Surové dumpy pro úplnou rekonstrukci (volitelné)",
            "state": "ok" if not raw_problems else "optional",
            "detail": {
                "problems": raw_problems,
                "download_mb": round(download_size_mb(status=raw)),
            },
            "step": "rebuild",
        },
        {
            "id": "hf_token",
            "label": "Token Hugging Face (volitelné)",
            "state": "ok" if _hf_token_present() else "info",
            "detail": {
                "present": _hf_token_present(),
                "note": "Oba stahované modely jsou veřejné; token je třeba jen pro gated modely nebo když Hugging Face omezí anonymní stahování.",
            },
            "step": None,
        },
        {
            "id": "clis",
            "label": "CLI poskytovatelů modelů (volitelné)",
            "state": "info",
            "detail": {name: bool(s.get("available")) for name, s in clis.items()},
            "step": None,
        },
    ]
    return {
        "ready": packed_ok and db_ok,
        "checks": checks,
        "steps": STEPS,
        "plans": {name: list(steps) for name, steps in PLANS.items()},
        "running": (jobs.running("setup") or jobs.Job(id="", kind="", label="")).id or None,
    }


@router.get("/setup/status")
def setup_status() -> dict[str, Any]:
    """What a fresh clone still lacks; ``ready`` is true when the page can run."""
    return status_payload()


# ---------------------------------------------------------------------------
# Running the steps
# ---------------------------------------------------------------------------


def _stream(cmd: list[str], progress: jobs.ProgressFn, done: int, total: int) -> None:
    """Run one pipeline command and pass its lines to the job log; fail on a non-zero exit."""
    progress(done, total, "$ " + " ".join(cmd[1:]))
    proc = subprocess.Popen(
        cmd, cwd=THESIS_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    tail: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            tail = (tail + [line])[-5:]
            progress(done, total, line)
    if proc.wait() != 0:
        raise RuntimeError(f"{cmd[2]} exited with {proc.returncode}: " + " | ".join(tail))


def _download_or_hint(load):
    """Run a model loader; turn a Hugging Face 401/403/429 into one sentence that names the fix."""
    from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

    try:
        return load()
    except (GatedRepoError, HfHubHTTPError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(exc, GatedRepoError) or status in (401, 403, 429):
            raise RuntimeError(
                f"Hugging Face odmítl stažení ({status or 'gated'}): uložte token na obrazovce "
                "Instalace (pole Token Hugging Face) a krok spusťte znovu."
            ) from exc
        raise


def _run_step(name: str, progress: jobs.ProgressFn, done: int, total: int) -> None:
    """Run one named setup step (``unpack``, ``database``, ``rebuild``, ``ner``, ``whisper``)."""
    if name == "unpack":
        for path in packing.ensure_unpacked(announce=False):
            progress(done, total, f"unpacked {path.relative_to(THESIS_ROOT)}")
        progress(done, total, "snapshots unpacked")
    elif name == "database":
        _stream(
            [sys.executable, "-m", "substrate.pipeline.build_all", "--force", "--from", "database"],
            progress,
            done,
            total,
        )
    elif name == "rebuild":
        _stream(
            [sys.executable, "-m", "substrate.pipeline.build_all", "--force"], progress, done, total
        )
    elif name == "ner":
        from ucs.uc02_pseudonymization.code.pseudonymizer import pseudonymize

        progress(done, total, f"loading {_NER_MODEL} (downloads on first use)")
        masked, _ = _download_or_hint(
            lambda: pseudonymize("Jan Novák z Brna, telefon 602 123 456.", use_ner=True)
        )
        progress(done, total, f"NER ready: {masked}")
    elif name == "whisper":
        from ucs.uc03_mcp_privacy import stt

        progress(
            done,
            total,
            f"loading faster-whisper {uc03_config.WHISPER_MODEL} (downloads on first use)",
        )
        _download_or_hint(
            lambda: stt.transcribe_pcm(
                bytes(uc03_config.SAMPLE_RATE * uc03_config.SAMPLE_WIDTH_BYTES), backend="whisper"
            )
        )
        progress(done, total, "Whisper ready")
    else:
        raise ValueError(f"unknown setup step {name!r}")


@router.post("/setup/hf-token")
def setup_hf_token(req: HfTokenRequest) -> dict[str, Any]:
    """Store a Hugging Face token where the hub client reads it (``~/.cache/huggingface/token``)."""
    from huggingface_hub import login, whoami

    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="empty token")
    try:
        login(token=token, add_to_git_credential=False)
        user = whoami(token=token).get("name")
    except Exception as exc:  # noqa: BLE001 - an invalid token is the user's to fix
        raise HTTPException(status_code=400, detail=f"hf_token_rejected: {exc}") from exc
    return {"saved": True, "user": user}


@router.post("/setup/run")
def setup_run(req: SetupRunRequest) -> dict[str, Any]:
    """Run the chosen steps (or a plan) in order as one background job."""
    steps = list(req.steps or [])
    if req.plan:
        if req.plan not in PLANS:
            raise HTTPException(
                status_code=400, detail=f"unknown_plan: {req.plan}; known: {list(PLANS)}"
            )
        steps = list(PLANS[req.plan])
    unknown = [s for s in steps if s not in STEPS]
    if not steps or unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown_setup_steps: {unknown or 'none given'}"
        )
    total = len(steps)

    def target(progress: jobs.ProgressFn) -> dict[str, Any]:
        """Run every chosen step in order, reporting progress after each one."""
        for index, name in enumerate(steps):
            progress(index, total, f"== {STEPS[name]['label']}")
            _run_step(name, progress, index, total)
        progress(total, total, "hotovo")
        return {"steps": steps, "ready": status_payload()["ready"]}

    job = jobs.start(
        "setup", "Instalace · " + ", ".join(steps), target, total=total, exclusive=True
    )
    return {"job": job.to_dict(), "steps": steps}
