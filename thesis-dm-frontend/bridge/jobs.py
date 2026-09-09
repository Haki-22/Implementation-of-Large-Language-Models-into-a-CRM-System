"""Background jobs of the bridge: a run that does not fit an HTTP request.

The UC-01 ladder, the UC-04 arena, the UC-04 model methods and the installation take
minutes. A route starts one as a job and answers with its id at once; the page polls
``GET /jobs/{id}`` for the state, the progress and the log tail. The run folder the
runner writes is the result and the only durable record; the registry lives in the
bridge process and keeps the last ``KEEP_FINISHED`` finished jobs.

One job at a time per kind: a second request while one runs answers 409. A job started
as ``exclusive`` (the installation, which rewrites files every route reads) refuses to
start while anything else runs and blocks every other job and model turn until it ends.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

LOG_TAIL = 60
KEEP_FINISHED = 50

ProgressFn = Callable[..., None]
"""``progress(done, total=None, line=None)``: counts and an optional log line."""


# ---------------------------------------------------------------------------
# The job record
# ---------------------------------------------------------------------------


def _now() -> str:
    """Current UTC time as a second-precision ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    """One background run and what the page needs to know about it."""

    id: str
    kind: str
    label: str
    exclusive: bool = False
    state: str = "queued"  # queued | running | done | failed
    created: str = field(default_factory=_now)
    started: str | None = None
    finished: str | None = None
    done: int = 0
    total: int | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=LOG_TAIL))
    result: dict[str, Any] | None = None
    error: str | None = None
    thread_id: int | None = None
    started_monotonic: float | None = None
    probe: Callable[[], tuple[int, int | None]] | None = None
    """Optional: computes ``(done, total)`` on demand for runners without a callback."""

    @property
    def active(self) -> bool:
        """True while the job is still queued or running."""
        return self.state in ("queued", "running")

    def progress(self, done: int, total: int | None = None, line: str | None = None) -> None:
        """The runner's callback: counts and an optional log line, under the registry lock."""
        with _LOCK:
            self.done = done
            if total is not None:
                self.total = total
            if line:
                self.log.append(line)

    def to_dict(self) -> dict[str, Any]:
        """A snapshot for the page, taken under the registry lock so a worker cannot tear it."""
        with _LOCK:
            done, total = self.done, self.total
            elapsed = (
                round(time.monotonic() - self.started_monotonic, 1)
                if self.started_monotonic is not None and self.state == "running"
                else None
            )
            snapshot = {
                "id": self.id,
                "kind": self.kind,
                "label": self.label,
                "exclusive": self.exclusive,
                "state": self.state,
                "created": self.created,
                "started": self.started,
                "finished": self.finished,
                "elapsed_seconds": elapsed,
                "log": list(self.log),
                "result": self.result,
                "error": self.error,
            }
        if self.probe is not None and snapshot["state"] == "running":
            try:
                done, total = self.probe()
            except Exception:  # noqa: BLE001 - a probe must never break the poll
                pass
        snapshot["done"], snapshot["total"] = done, total
        return snapshot


# ---------------------------------------------------------------------------
# Log capture: the runners log through ``logging``; the job keeps its thread's lines
# ---------------------------------------------------------------------------


class _JobLogHandler(logging.Handler):
    """Appends the log records emitted by the job's thread to the job's log tail."""

    def __init__(self, job: Job) -> None:
        """Attach this handler to ``job``; only records from the job's own thread are kept."""
        super().__init__(level=logging.INFO)
        self.job = job

    def emit(self, record: logging.LogRecord) -> None:
        """Forward the record's message to the job's log tail, ignoring other threads."""
        if record.thread != self.job.thread_id:
            return
        try:
            self.job.progress(self.job.done, None, record.getMessage())
        except Exception:  # noqa: BLE001 - formatting must never break the runner
            pass


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

_JOBS: dict[str, Job] = {}
_LOCK = threading.RLock()


def running(kind: str) -> Job | None:
    """The active job of ``kind``, if any."""
    with _LOCK:
        return next((j for j in _JOBS.values() if j.kind == kind and j.active), None)


def maintenance_running() -> Job | None:
    """The active exclusive job (the installation), if any."""
    with _LOCK:
        return next((j for j in _JOBS.values() if j.exclusive and j.active), None)


def require_no_maintenance() -> None:
    """409 while the installation rewrites the files a model turn would read."""
    busy = maintenance_running()
    if busy is not None:
        raise HTTPException(
            status_code=409,
            detail=f"maintenance_running: běží instalace ({busy.id}); počkejte, až doběhne.",
        )


def _prune() -> None:
    """Drop the oldest finished jobs beyond ``KEEP_FINISHED``, keeping the registry bounded."""
    finished = [j for j in _JOBS.values() if not j.active]
    for job in sorted(finished, key=lambda j: j.created)[: max(0, len(finished) - KEEP_FINISHED)]:
        _JOBS.pop(job.id, None)


def start(
    kind: str,
    label: str,
    target: Callable[[ProgressFn], dict[str, Any]],
    *,
    total: int | None = None,
    probe: Callable[[], tuple[int, int | None]] | None = None,
    exclusive: bool = False,
) -> Job:
    """Run ``target(progress)`` in a worker thread and return the job at once.

    ``target`` returns the result dict (at least ``run_dir``); an exception fails the job
    with its message and traceback tail in the log.
    """
    with _LOCK:
        busy = running(kind)
        if busy is not None:
            raise HTTPException(
                status_code=409,
                detail=f"job_running: {kind} už běží jako {busy.id}; počkejte, až doběhne.",
            )
        require_no_maintenance()
        if exclusive and any(j.active for j in _JOBS.values()):
            raise HTTPException(
                status_code=409,
                detail="jobs_running: instalace čeká, až doběhnou rozběhnuté běhy.",
            )
        _prune()
        job = Job(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            label=label,
            exclusive=exclusive,
            total=total,
            probe=probe,
        )
        _JOBS[job.id] = job

    def _work() -> None:
        """Run ``target`` on the worker thread, capturing its log lines and final state."""
        with _LOCK:
            job.thread_id = threading.get_ident()
            job.state = "running"
            job.started = _now()
            job.started_monotonic = time.monotonic()
        handler = _JobLogHandler(job)
        logging.getLogger().addHandler(handler)
        try:
            result = target(job.progress)
            with _LOCK:
                job.result = result
                job.state = "done"
        except Exception as exc:  # noqa: BLE001 - the page shows every failure
            with _LOCK:
                job.error = f"{type(exc).__name__}: {exc}"
                job.log.extend(traceback.format_exc().strip().splitlines()[-8:])
                job.state = "failed"
            logger.exception("job %s (%s) failed", job.id, job.kind)
        finally:
            with _LOCK:
                job.finished = _now()
            logging.getLogger().removeHandler(handler)

    threading.Thread(target=_work, name=f"job-{kind}-{job.id}", daemon=True).start()
    return job


def get(job_id: str) -> Job:
    """The job by id; 404 when unknown (finished jobs beyond ``KEEP_FINISHED`` are gone)."""
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}")
    return job


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/jobs")
def list_jobs() -> dict[str, Any]:
    """Every job this bridge process still holds, newest first."""
    with _LOCK:
        jobs = sorted(_JOBS.values(), key=lambda j: j.created, reverse=True)
    return {"jobs": [j.to_dict() for j in jobs]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """State, progress, log tail and result of one job."""
    return get(job_id).to_dict()
