"""UC-04 routes: the arena as the page drives it.

Arms and methods come from the registries; a classical run and a model run are jobs on
``arena.run`` and ``model_arena.run``; the run folders under ``eval/runs/`` are read as
they are. A model run started from the page carries ``role="comparison"`` and a sample
limit, so it can never become the run of record, and every page run refreshes its
appendix files under the bridge's runtime folder, never under ``attachments/``.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import jobs
from common import (
    PAGE_ATTACHMENTS_DIR,
    ModelChoice,
    check_provider,
    connect_db,
    db_rows,
    folder_or_404,
    read_json,
    read_text,
    require_llm_calls_on,
    run_folders,
)
from ucs.uc04_matchmaker import arena, attachment, model_arena
from ucs.uc04_matchmaker import arms as arm_registry
from ucs.uc04_matchmaker import data as uc04_data
from ucs.uc04_matchmaker.arms import model as model_registry
from ucs.uc04_matchmaker.sample import DEFAULT_SAMPLE, load_sample
from utils.paths import UC04_DIR, UC04_HANDOFF

router = APIRouter()

RUNS_DIR = attachment.RUNS_DIR
_EVAL_DIR = UC04_DIR / "eval"
_TOP_K = 10


# ---------------------------------------------------------------------------
# Request shapes
# ---------------------------------------------------------------------------


class ArenaRunRequest(BaseModel):
    """A classical run: arms, branches, regimes. No model call."""

    arms: list[str] = ["popularity", "als_cf"]
    langs: list[str] = ["en", "cs"]
    regimes: list[str] = ["crm"]


class ModelRunRequest(ModelChoice):
    """A model-method run on a sample of the fixed 100; always a comparison, never the record."""

    methods: list[str] = ["rerank_als"]
    langs: list[str] = ["en"]
    limit: int = 10


# ---------------------------------------------------------------------------
# Arms and methods
# ---------------------------------------------------------------------------


@router.get("/uc04/arms")
def uc04_arms() -> dict[str, Any]:
    """The classical arms and the model methods, straight from the registries."""
    classical = [
        {
            "name": name,
            "title": module.TITLE,
            "description": getattr(module, "DESCRIPTION", ""),
            "family": getattr(module, "FAMILY", ""),
            "slow": name in arm_registry.SLOW,
            "supports_population": bool(getattr(module, "SUPPORTS_POPULATION", False)),
        }
        for name, module in arm_registry.ARMS.items()
    ]
    methods = [
        {
            "name": name,
            "title": module.TITLE,
            "description": getattr(module, "DESCRIPTION", ""),
            "family": getattr(module, "FAMILY", ""),
            "ml_input": getattr(module, "ML_INPUT", None),
            "protocols": list(getattr(module, "PROTOCOLS", ())),
            "subset": getattr(module, "SUBSET", None),
        }
        for name, module in model_registry.MODEL_ARMS.items()
    ]
    return {
        "classical": classical,
        "methods": methods,
        "regimes": list(arena.REGIMES),
        "protocols": list(arena.PROTOCOLS),
        "sample": DEFAULT_SAMPLE,
    }


# ---------------------------------------------------------------------------
# Runs as jobs
# ---------------------------------------------------------------------------


@router.post("/uc04/run")
def uc04_run(req: ArenaRunRequest) -> dict[str, Any]:
    """Run classical arms into a new run folder as a job (no model calls).

    The folder carries ``role="comparison"``: it sits beside the records under
    ``eval/runs/`` but is never selected as the run of record.
    """
    arms = [a.strip() for a in req.arms if a.strip()]
    unknown = [a for a in arms if a not in arm_registry.ARMS]
    if not arms or unknown:
        raise HTTPException(status_code=400, detail=f"unknown_uc04_arms: {unknown or 'none given'}")
    langs = [lang for lang in req.langs if lang in ("en", "cs")] or ["en"]
    regimes = [r for r in req.regimes if r in arena.REGIMES] or ["crm"]

    def target(progress: jobs.ProgressFn) -> dict[str, Any]:
        """Run the classical arms into a new comparison run folder."""
        folder = arena.run(
            arms=arms,
            langs=langs,
            regimes=regimes,
            attachments_dir=PAGE_ATTACHMENTS_DIR,
            progress=lambda done, total: progress(done, total),
            role="comparison",
        )
        return {"run_dir": folder.name, "kind": "arena"}

    total = sum(
        len(langs)
        for regime in regimes
        for name in arms
        if regime != "population" or arm_registry.ARMS[name].SUPPORTS_POPULATION
    )
    job = jobs.start(
        "uc04-arena", f"UC-04 aréna · {', '.join(arms)} · {', '.join(langs)}", target, total=total
    )
    return {"job": job.to_dict()}


@router.post("/uc04/model-run")
def uc04_model_run(req: ModelRunRequest) -> dict[str, Any]:
    """Run model methods on a sample as a comparison job; switch-gated unless mock."""
    check_provider(req.provider)
    methods = [m.strip() for m in req.methods if m.strip()]
    unknown = [m for m in methods if m not in model_registry.MODEL_ARMS]
    if not methods or unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown_uc04_methods: {unknown or 'none given'}"
        )
    langs = [lang for lang in req.langs if lang in ("en", "cs")] or ["en"]
    limit = max(1, min(int(req.limit), 100))
    require_llm_calls_on(req.provider)
    started_at = time.time()

    def target(progress: jobs.ProgressFn) -> dict[str, Any]:
        """Run the model methods on the sample into a new comparison run folder."""
        folder = model_arena.run(
            methods=methods,
            langs=langs,
            provider=req.provider,
            model=req.model,
            tier=req.tier,
            limit=limit,
            role="comparison",
            attachments_dir=PAGE_ATTACHMENTS_DIR,
        )
        return {"run_dir": folder.name, "kind": "model"}

    total = len(methods) * len(langs) * limit

    def probe() -> tuple[int, int | None]:
        """Count recorded calls in the newest model-methods folder, for a runner with no callback."""
        # The model runner has no callback; count the recorded calls of the newest
        # model-methods folder created after the job started.
        newest = None
        for folder in run_folders(RUNS_DIR):
            if "model-methods" in folder.name and folder.stat().st_mtime >= started_at - 1:
                newest = folder
                break
        if newest is None:
            return 0, total
        calls = newest / "calls"
        done = sum(1 for _ in calls.glob("*/*.json")) if calls.exists() else 0
        return min(done, total), total

    job = jobs.start(
        "uc04-model",
        f"UC-04 modelové metody · {', '.join(methods)} · {req.provider} · {limit} zákazníků",
        target,
        total=total,
        probe=probe,
    )
    return {"job": job.to_dict()}


# ---------------------------------------------------------------------------
# Run folders
# ---------------------------------------------------------------------------


def _kind(name: str) -> str:
    """Classify a run folder name by the substring it contains (arena, model, outputs, ...)."""
    for key, kind in (
        ("-arena-", "arena"),
        ("model-methods", "model"),
        ("outputs-for-uc01", "outputs"),
        ("data-facts", "facts"),
        ("personality", "personality"),
        ("smoke", "smoke"),
    ):
        if key in name:
            return kind
    return "other"


@router.get("/uc04/runs")
def uc04_runs(kind: str | None = None) -> dict[str, Any]:
    """Run folders under ``eval/runs/`` with their configuration in short."""
    newest_full = attachment.newest_full_run()
    runs = []
    for folder in run_folders(RUNS_DIR):
        run_kind = _kind(folder.name)
        if kind and run_kind != kind:
            continue
        cfg = read_json(folder / "config.json", {}) or {}
        runs.append(
            {
                "name": folder.name,
                "kind": run_kind,
                "date": cfg.get("date") or cfg.get("created"),
                "arms": list(cfg.get("arms", {}) or {}),
                "methods": list(cfg.get("methods", {}) or {}),
                "languages": cfg.get("languages"),
                "regimes": cfg.get("regimes"),
                "provider": cfg.get("provider"),
                "model": cfg.get("model"),
                "tier": cfg.get("tier"),
                "role": cfg.get("role"),
                "limit": cfg.get("limit"),
                "customers": (cfg.get("sample") or {}).get("customers")
                and len((cfg.get("sample") or {}).get("customers", [])),
                "total_seconds": cfg.get("total_seconds"),
                "has_card": (folder / "RESULTS.md").exists(),
                "record": newest_full is not None and folder.name == newest_full.name,
            }
        )
    return {"runs": runs, "record_arena": newest_full.name if newest_full else None}


@router.get("/uc04/runs/{name}")
def uc04_run_detail(name: str) -> dict[str, Any]:
    """The card, the table and the flattened rows of one run folder."""
    folder = folder_or_404(RUNS_DIR, name)
    kind = _kind(name)
    rows: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    config: dict[str, Any] = read_json(folder / "config.json", {}) or {}
    if kind == "arena" and (folder / "scores").exists():
        config, rows = attachment.arena_rows(folder)
    elif kind == "model" and (folder / "scores").exists():
        config, results, pairs = model_arena.load_run(folder)
        for key, entry in results.items():
            if key.startswith("reference-"):
                continue
            for proto, res in (entry.get("protocols") or {}).items():
                rows.append(
                    {
                        "method": entry.get("method"),
                        "branch": entry.get("lang"),
                        "protocol": proto,
                        "customers": res.get("n_customers"),
                        "hits_top5": (res.get("hits") or {}).get("5"),
                        "hits_top10": (res.get("hits") or {}).get("10"),
                        "hr_top10": res.get("hr", {}).get("10"),
                        "calls": entry.get("calls"),
                        "median_call_seconds": entry.get("median_call_seconds"),
                        "seconds": entry.get("wall_seconds"),
                    }
                )
    slim_config = {
        k: v
        for k, v in config.items()
        if k not in ("prompts", "code", "database", "population", "czech_branch")
    }
    return {
        "name": folder.name,
        "kind": kind,
        "card": read_text(folder / "RESULTS.md"),
        "table": read_text(folder / "TABLE.md"),
        "rows": rows,
        "pairs": pairs,
        "config": slim_config,
    }


# ---------------------------------------------------------------------------
# Customers: the hidden item against each arm's list
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    """The product catalog keyed by ASIN, loaded once and cached for the process's lifetime."""
    conn = connect_db()
    try:
        return uc04_data.load_catalog(conn)
    finally:
        conn.close()


def _title(asin: str, lang: str) -> str:
    """The catalog title of ``asin`` in ``lang`` ('en' or 'cs'), falling back to the ASIN itself."""
    entry = _catalog().get(asin) or {}
    if lang == "cs":
        return entry.get("title_cs") or entry.get("title") or asin
    return entry.get("title") or asin


def _run_per_customer(folder) -> dict[str, list[dict[str, Any]]]:
    """``scores/*.json`` of a run → per-customer entries keyed by the score file's stem."""
    out: dict[str, list[dict[str, Any]]] = {}
    scores = folder / "scores"
    if not scores.exists():
        return out
    for path in sorted(scores.glob("*.json")):
        if path.stem.startswith("reference-"):
            continue
        entry = read_json(path, {}) or {}
        detail = entry.get("per_customer") or {}
        for proto, rows in detail.items():
            for row in rows or []:
                out.setdefault(str(row.get("contact_id")), []).append(
                    {
                        "key": path.stem,
                        "arm": entry.get("arm") or entry.get("method"),
                        "regime": entry.get("regime"),
                        "branch": entry.get("lang"),
                        "protocol": proto,
                        "rank": row.get("rank"),
                        "held_out": row.get("held_out"),
                        "top10": row.get("top10") or [],
                    }
                )
    return out


@lru_cache(maxsize=1)
def _handoff_by_contact() -> dict[int, dict[str, Any]]:
    """The UC-04 handoff file's user entries reindexed by ``contact_id``, cached once loaded."""
    handoff = read_json(UC04_HANDOFF, {}) or {}
    users = handoff.get("users", {}) if isinstance(handoff, dict) else {}
    out: dict[int, dict[str, Any]] = {}
    for reviewer_id, payload in users.items():
        cid = payload.get("contact_id")
        if cid is not None:
            out[int(cid)] = {**payload, "reviewer_id": reviewer_id}
    return out


def _resolve_run(run: str | None):
    """The named run folder, or the newest full (non-comparison) run if none is named."""
    if run:
        return folder_or_404(RUNS_DIR, run)
    folder = attachment.newest_full_run()
    if folder is None:
        raise HTTPException(status_code=404, detail="no full arena run under eval/runs/")
    return folder


@router.get("/uc04/customers")
def uc04_customers(
    scope: str = "pick", q: str = "", run: str | None = None, limit: int = 40
) -> dict[str, Any]:
    """Customers with their hidden item: the UC-01 pick's linked contacts, the model sample, or a search."""
    from routes_uc01 import _pick, _pick_ids

    limit = max(1, min(limit, 200))
    folder = _resolve_run(run)
    per_customer = _run_per_customer(folder)
    query = q.strip()
    if query:
        like = f"%{query}%"
        rows = db_rows(
            "SELECT id, first_name, last_name, city, amazon_group FROM uc_contacts "
            "WHERE first_name LIKE ? OR last_name LIKE ? OR first_name || ' ' || last_name LIKE ? "
            "ORDER BY id LIMIT ?",
            (like, like, like, limit),
        )
        ids = [int(r["id"]) for r in rows]
        scope = "all"
    elif scope == "sample":
        ids = list(load_sample()["contact_ids"])[:limit]
    else:
        pick = _pick()
        ids = [
            cid
            for cid in _pick_ids(pick)
            if (pick["contacts"].get(str(cid)) or {}).get("tier") == "linked"
        ]
        scope = "pick"
    placeholders = ",".join("?" for _ in ids) or "NULL"
    rows = db_rows(
        f"SELECT id, first_name, last_name, city, amazon_group FROM uc_contacts WHERE id IN ({placeholders})",  # noqa: S608
        tuple(ids),
    )
    by_id = {int(r["id"]): r for r in rows}
    handoff = _handoff_by_contact()
    customers = []
    for cid in ids:
        r = by_id.get(cid)
        if r is None:
            continue
        entries = per_customer.get(str(cid), [])
        held = entries[0]["held_out"] if entries else None
        customers.append(
            {
                "id": cid,
                "name": f"{r['first_name']} {r['last_name']}".strip(),
                "city": r.get("city"),
                "group": r.get("amazon_group"),
                "in_run": bool(entries),
                "hidden": {
                    "asin": held,
                    "title": _title(held, "en"),
                    "title_cs": _title(held, "cs"),
                }
                if held
                else None,
                "has_handoff": cid in handoff,
            }
        )
    return {"scope": scope, "run": folder.name, "customers": customers}


@router.get("/uc04/customers/{contact_id}")
def uc04_customer(contact_id: int, run: str | None = None) -> dict[str, Any]:
    """The hidden item and each arm's list for one customer in one run, plus the handoff lines."""
    folder = _resolve_run(run)
    entries = _run_per_customer(folder).get(str(contact_id), [])
    row = db_rows(
        "SELECT id, first_name, last_name, city, amazon_group FROM uc_contacts WHERE id = ?",
        (contact_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"contact_not_found: {contact_id}")
    held = entries[0]["held_out"] if entries else None
    arms_out = []
    for e in entries:
        lang = e["branch"] or "en"
        top = [
            {
                "asin": asin,
                "title": _title(asin, lang),
                "hit": asin == e["held_out"],
            }
            for asin in e["top10"][:_TOP_K]
        ]
        arms_out.append({**e, "top10": top, "hit_in_top10": any(t["hit"] for t in top)})
    handoff = _handoff_by_contact().get(contact_id)
    handoff_out = None
    if handoff:
        handoff_out = {
            "reviewer_id": handoff.get("reviewer_id"),
            "recommendations": handoff.get("topk_recommendations", [])[:5],
            "persona": handoff.get("persona"),
            "aspects": handoff.get("aspects"),
            "topic_clusters": handoff.get("topic_clusters", [])[:5],
            "lifecycle": handoff.get("lifecycle"),
        }
    r = row[0]
    return {
        "run": folder.name,
        "contact": {
            "id": contact_id,
            "name": f"{r['first_name']} {r['last_name']}".strip(),
            "city": r.get("city"),
            "group": r.get("amazon_group"),
        },
        "hidden": {"asin": held, "title": _title(held, "en"), "title_cs": _title(held, "cs")}
        if held
        else None,
        "arms": arms_out,
        "handoff": handoff_out,
    }


@router.get("/uc04/results")
def uc04_results() -> dict[str, Any]:
    """The one-page card generated from the runs of record."""
    handoff_meta = (read_json(UC04_HANDOFF, {}) or {}).get("_meta", {})
    return {
        "card": read_text(_EVAL_DIR / "RESULTS.md"),
        "handoff_meta": handoff_meta,
        "source": str(_EVAL_DIR),
    }
