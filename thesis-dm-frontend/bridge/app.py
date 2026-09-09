"""FastAPI backend of the thesis demo page.

The page in ``thesis-dm-frontend/`` is built on these routes alone: no mock data, no
client-side fallback. Every route calls the same plain function the use-case CLIs call;
every route that can reach a paid provider checks the process-wide model-call switch;
runs that take minutes are background jobs whose run folder is the result.

Routes
------
- ``/generation/*``, ``/llm-switch``   the model catalog and the switch (``routes_generation``)
- ``/jobs``                              background runs (``jobs``)
- ``/uc01/*``                            personalisation ladder (``routes_uc01``)
- ``/uc02/*``                            reversible pseudonymisation (``routes_uc02``)
- ``/uc03/*``                            MCP chat with the envelope, dictation, audit (``routes_uc03``)
- ``/uc04/*``                            recommendation arena (``routes_uc04``)
- ``/code/*``                            the code explainer (``routes_code``)
- ``/repo/*``                            the repository browser (``routes_repo``)
- ``/setup/*``                           the installation screen (``routes_setup``)
- ``/health``                            readiness
- ``/dm/``                               the page

Run
---
::

    cd thesis-dm-frontend/bridge
    ./run.sh
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# --- Project bootstrap: the thesis root (packages) and this folder (route modules) ---
_BASE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BASE_DIR.parents[1]
for entry in (str(_PROJECT_ROOT), str(_BASE_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)
# -------------------------------------------------------------------------------------

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import jobs  # noqa: E402
import routes_code  # noqa: E402
import routes_generation  # noqa: E402
import routes_history  # noqa: E402
import routes_repo  # noqa: E402
import routes_setup  # noqa: E402
import routes_uc01  # noqa: E402
import routes_uc02  # noqa: E402
import routes_uc03  # noqa: E402
import routes_uc04  # noqa: E402
from common import ensure_runtime_dirs  # noqa: E402
from ucs.uc01_personalization.picker import DEFAULT_PICK, pick_path  # noqa: E402
from utils.llm_switch import llm_calls_enabled  # noqa: E402
from utils.paths import (  # noqa: E402
    SUBSTRATE_DB,
    THESIS_ROOT,
    UC01_RUNS_DIR,
    UC02_PII_CORPUS_SNAPSHOT,
    UC04_HANDOFF,
)

_DM_FRONTEND = THESIS_ROOT / "thesis-dm-frontend"

app = FastAPI(title="Thesis DM frontend bridge")
for module in (
    routes_generation,
    jobs,
    routes_uc01,
    routes_uc02,
    routes_uc03,
    routes_uc04,
    routes_code,
    routes_repo,
    routes_setup,
    routes_history,
):
    app.include_router(module.router)

ensure_runtime_dirs()
# The runners log their steps at INFO; the job registry tails those lines for the page.
logging.getLogger("ucs").setLevel(logging.INFO)


@app.get("/health")
def health() -> dict[str, Any]:
    """Readiness: what the page can expect from this machine."""
    return {
        "ok": True,
        "substrate_db": SUBSTRATE_DB.exists(),
        "uc01_pick": pick_path(DEFAULT_PICK).exists(),
        "uc01_runs": UC01_RUNS_DIR.exists(),
        "uc02_corpus": UC02_PII_CORPUS_SNAPSHOT.exists(),
        "uc04_handoff": UC04_HANDOFF.exists(),
        "uc04_record_arena": routes_uc04.attachment.newest_full_run() is not None,
        "dm_frontend": _DM_FRONTEND.exists(),
        "llm_calls_enabled": llm_calls_enabled(),
        "uc03": routes_uc03.runtime_paths(),
    }


# Static page mounted last so the API routes win on collision.
if _DM_FRONTEND.exists():
    app.mount("/dm", StaticFiles(directory=_DM_FRONTEND, html=True), name="dm")


@app.get("/")
def root() -> RedirectResponse:
    """Open the page by default."""
    return RedirectResponse(url="/dm/", status_code=307)


@app.head("/")
def root_head() -> RedirectResponse:
    """The same redirect for HEAD probes."""
    return RedirectResponse(url="/dm/", status_code=307)
