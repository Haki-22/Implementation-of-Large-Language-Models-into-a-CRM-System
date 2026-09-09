"""UC-01 routes: the personalisation ladder as the page drives it.

Contacts and the person card come from ``substrate.db`` through UC-01's own loaders;
one message is ``generate()`` (the single call the runner also makes); the whole ladder
for one contact is a job on ``runner.run`` that reuses the record's identical calls;
the run folders under ``snapshots/runs/`` are read as they are.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

import jobs
from common import (
    ModelChoice,
    check_provider,
    connect_db,
    db_one,
    db_rows,
    folder_or_404,
    provider_http_error,
    read_json,
    read_text,
    require_llm_calls_on,
    run_folders,
)
from ucs.uc01_personalization import (
    card,
    data,
    judge,
    judge_run,
    levels,
    picker,
    runner,
)
from ucs.uc01_personalization.generate import generate
from utils.paths import UC01_DIR, UC01_RUNS_DIR

router = APIRouter()

TIER_LEVELS = frozenset({"0", "1", "2", "3", "5", "6"})
"""The rungs the assignment names; the other rungs are single-field arms."""


# ---------------------------------------------------------------------------
# Request shapes
# ---------------------------------------------------------------------------


class JudgeChoice(BaseModel):
    """Explicit cascade, with compatibility for the former single-model picker."""

    model_config = {"extra": "forbid"}
    level: Literal[0, 1, 2, 3] = 0
    judges: list[ModelChoice] = Field(default_factory=list)
    arbiter: ModelChoice | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_single_judge(cls, value: Any) -> Any:
        """Upgrade the old single-model judge payload (``{provider, ...}``) into a level-1 cascade."""
        if isinstance(value, dict) and "provider" in value and "level" not in value:
            return {"level": 1, "judges": [value]}
        return value


class GenerateRequest(ModelChoice):
    """One message for one contact at one level, from a brief row or a typed template."""

    contact_id: int
    brief_id: int | None = None
    custom_template: str | None = None
    level: str = "2"
    judge: JudgeChoice | None = None


class LadderRequest(ModelChoice):
    """The whole ladder (or a level list) for one contact, as a background job."""

    contact_id: int
    levels: str = "all"
    judge: JudgeChoice | None = None


def _selected_judge(choice: JudgeChoice | None) -> judge.Cascade | None:
    """Validate and gate an explicit judge, independently of the writer; no auto-selection."""
    if choice is None:
        return None
    if choice.level == 0:
        if choice.judges or choice.arbiter:
            raise HTTPException(
                status_code=400, detail="rules-only level takes no model judges"
            )
        return None
    choices = [*choice.judges, *([choice.arbiter] if choice.arbiter else [])]
    if any(
        any(
            name in (spec.model or "").lower()
            for name in ("claude", "sonnet", "opus", "haiku")
        )
        for spec in choices
        if spec.provider != "claude"
    ):
        raise HTTPException(
            status_code=400,
            detail="judge_model: Claude models are disabled, including via agy",
        )
    if any(spec.provider not in ("codex", "agy", "mock") for spec in choices):
        raise HTTPException(
            status_code=400, detail="judge_provider: choose codex or agy"
        )
    try:
        specs = [
            judge.JudgeSpec(**judge.JudgeSpec(s.provider, s.model, s.tier).resolved())
            for s in choice.judges
        ]
        arbiter = choice.arbiter
        arbiter_spec = (
            judge.JudgeSpec(
                **judge.JudgeSpec(
                    arbiter.provider, arbiter.model, arbiter.tier
                ).resolved()
            )
            if arbiter
            else None
        )
        if choice.level != 3 and arbiter_spec:
            raise ValueError("only level 3 takes an arbiter")
        if choice.level >= 2 and len({s.provider for s in specs}) != 2:
            raise ValueError("two judges must come from two different providers")
        cascade = judge.Cascade(choice.level, tuple(specs), arbiter_spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for spec in choices:
        require_llm_calls_on(spec.provider)
    return cascade


# ---------------------------------------------------------------------------
# Levels, contacts, briefs
# ---------------------------------------------------------------------------


@router.get("/uc01/levels")
def uc01_levels() -> dict[str, Any]:
    """The ladder in order: id, name, whether a model runs, the slots each rung needs."""
    return {
        "levels": [
            {
                "id": lvl.id,
                "name": lvl.name,
                "uses_model": lvl.uses_model,
                "needs": list(lvl.needs),
                "optional": list(lvl.optional),
                "tier": lvl.id in TIER_LEVELS,
            }
            for lvl in levels.LEVELS.values()
        ],
        "ladder": list(levels.LADDER),
    }


def _pick() -> dict[str, Any]:
    """The stored evaluation pick; 503 if it has not been built yet."""
    try:
        return picker.load_pick()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"pick_missing: {exc}") from exc


def _pick_ids(pick: dict[str, Any]) -> list[int]:
    """Every contact id the pick covers: the reading set plus every stratum."""
    return list(pick["reading_set"]) + [
        i for ids in pick["strata"].values() for i in ids
    ]


def _pick_membership(pick: dict[str, Any], contact_id: int) -> dict[str, Any] | None:
    """``contact_id``'s tier, stratum, and UC-04/Czech-review flags within the pick, or None."""
    member = pick.get("contacts", {}).get(str(contact_id))
    if member is None:
        return None
    stratum = next(
        (name for name, ids in pick.get("strata", {}).items() if contact_id in ids),
        None,
    )
    return {
        "tier": member.get("tier"),
        "stratum": stratum
        or ("reading" if contact_id in pick.get("reading_set", []) else None),
        "has_uc04": member.get("has_uc04"),
        "has_czech": member.get("has_czech"),
    }


def _contact_row_to_list(
    row: dict[str, Any], pick: dict[str, Any] | None
) -> dict[str, Any]:
    """Shrink one ``uc_contacts`` row to the fields a contact list card needs."""
    first, last = row.get("first_name") or "", row.get("last_name") or ""
    return {
        "id": int(row["id"]),
        "name": f"{first} {last}".strip() or f"Kontakt {row['id']}",
        "city": row.get("city"),
        "gender": row.get("gender"),
        "formal": bool(row["formal"]) if row.get("formal") is not None else None,
        "is_clean": bool(row.get("is_clean")),
        "lifecycle_stage": row.get("lifecycle_stage"),
        "amazon_group": row.get("amazon_group"),
        "pick": _pick_membership(pick, int(row["id"])) if pick else None,
    }


@router.get("/uc01/contacts")
def uc01_contacts(scope: str = "pick", q: str = "", limit: int = 30) -> dict[str, Any]:
    """Contacts to choose from: the pick's by default, or a search across every contact."""
    limit = max(1, min(limit, 100))
    query = q.strip()
    pick = _pick()
    if scope == "pick" and not query:
        ids = _pick_ids(pick)
        placeholders = ",".join("?" for _ in ids)
        rows = db_rows(
            f"SELECT * FROM uc_contacts WHERE id IN ({placeholders})",
            tuple(ids),  # noqa: S608
        )
        by_id = {int(r["id"]): r for r in rows}
        ordered = [by_id[i] for i in ids if i in by_id]
        return {
            "scope": "pick",
            "pick": pick["name"],
            "contacts": [_contact_row_to_list(r, pick) for r in ordered],
        }
    like = f"%{query}%"
    rows = db_rows(
        """
        SELECT * FROM uc_contacts
        WHERE (? = '' OR first_name LIKE ? OR last_name LIKE ?
               OR first_name || ' ' || last_name LIKE ? OR city LIKE ? OR email LIKE ?)
        ORDER BY is_clean DESC,
                 CASE WHEN first_name || ' ' || last_name LIKE ? THEN 0
                      WHEN last_name LIKE ? THEN 1 ELSE 2 END,
                 id
        LIMIT ?
        """,
        (query, like, like, like, like, like, f"{query}%", f"{query}%", limit),
    )
    return {
        "scope": "all",
        "query": query,
        "contacts": [_contact_row_to_list(r, pick) for r in rows],
    }


@router.get("/uc01/contacts/{contact_id}")
def uc01_contact(contact_id: int) -> dict[str, Any]:
    """The person card: identity, orders, words, reviews, OCEAN, which rungs can run."""
    row = db_one("SELECT * FROM uc_contacts WHERE id = ?", (contact_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"contact_not_found: {contact_id}")
    conn = connect_db()
    try:
        contact = data.load_contact(conn, contact_id)
        enrichment = data.load_enrichment(conn, contact)
        purchases = data.recent_purchases(conn, contact_id, limit=5)
        orders = conn.execute(
            "SELECT COUNT(*) FROM uc_orders WHERE contact_id = ?", (contact_id,)
        ).fetchone()[0]
        reviews = conn.execute(
            "SELECT COUNT(*) FROM uc_reviews WHERE contact_id = ?", (contact_id,)
        ).fetchone()[0]
        review_sample = data.czech_review_text(conn, contact_id, max_chars=400)
    finally:
        conn.close()
    present = enrichment.present()
    can_run = []
    for lvl in levels.LEVELS.values():
        missing = lvl.missing(contact, enrichment)
        can_run.append({"level": lvl.id, "ok": not missing, "missing": missing})
    pick = _pick()
    return {
        "id": contact.id,
        "name": f"{contact.first_name} {contact.last_name}".strip(),
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "name_vocative": contact.name_vocative,
        "gender": contact.gender,
        "formal": contact.formal,
        "is_clean": contact.is_clean,
        "title": contact.title,
        "employer": contact.employer,
        "lifecycle_stage": contact.lifecycle_stage,
        "lifecycle_label": contact.lifecycle_label,
        "city": row.get("city"),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "amazon_group": contact.amazon_group,
        "orders": orders,
        "purchases": purchases,
        "frequent_words": contact.frequent_words,
        "style_excerpt": contact.style_excerpt,
        "reviews": reviews,
        "review_sample": review_sample,
        "ocean": contact.ocean,
        "ocean_source": contact.ocean_source,
        "reviewer_gender": contact.reviewer_gender,
        "gender_paired": contact.gender_paired,
        "enrichment_present": sorted(present),
        "recommendations": enrichment.recommendations[:5],
        "topics": enrichment.topics[:5],
        "aspects": enrichment.aspects[:5],
        "pricing": enrichment.pricing,
        "levels": can_run,
        "pick": _pick_membership(pick, contact.id),
    }


@router.get("/uc01/briefs")
def uc01_briefs() -> dict[str, Any]:
    """Every message brief with its category; the pick's ladder briefs are marked."""
    pick = _pick()
    ladder = {int(b) for b in pick.get("briefs", [])}
    rows = db_rows("SELECT * FROM uc_message_briefs ORDER BY id")
    return {
        "briefs": [
            {
                "id": int(r["id"]),
                "title": r["title"],
                "category": r.get("category"),
                "default_template": r["default_template"],
                "ladder": int(r["id"]) in ladder,
            }
            for r in rows
        ],
        "ladder_briefs": pick.get("brief_titles", {}),
    }


# ---------------------------------------------------------------------------
# One message, the whole ladder
# ---------------------------------------------------------------------------


@router.post("/uc01/generate")
async def uc01_generate(req: GenerateRequest) -> dict[str, Any]:
    """Generate once, then optionally judge the result with an independently selected model."""
    check_provider(req.provider)
    cascade = _selected_judge(req.judge)
    level = str(req.level).strip().lower().lstrip("l")
    if level not in levels.LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown_level: {req.level}; choose from {list(levels.LADDER)}",
        )
    brief = None
    brief_id = req.brief_id or 0
    if req.custom_template and req.custom_template.strip():
        brief = data.Brief(
            0, "custom_page_message", "custom", req.custom_template.strip()
        )
    elif not req.brief_id:
        raise HTTPException(
            status_code=400, detail="brief_id or custom_template is required"
        )
    if levels.LEVELS[level].uses_model:
        require_llm_calls_on(req.provider)
    jobs.require_no_maintenance()
    try:
        gen = await generate(
            req.contact_id,
            brief_id,
            level,
            provider=req.provider,
            model=req.model,
            tier=req.tier,
            judges=("rules",),
            brief=brief,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise provider_http_error(exc, prefix="uc01_generate_failed") from exc
    payload = gen.to_dict()
    payload["judge_config"] = cascade.to_dict() if cascade else None
    payload["judgment"] = None
    if cascade and gen.ok:
        conn = data.connect()
        try:
            contact = data.load_contact(conn, req.contact_id)
        finally:
            conn.close()
        verdict = await judge.judge_cascade(gen.text, contact, cascade)
        payload["judgment"] = verdict.to_dict()
    payload["brief"] = {
        "id": brief_id,
        "title": brief.title if brief else None,
        "category": brief.category if brief else None,
    }
    payload["backend"] = "ucs.uc01_personalization.generate.generate + utils.generation"
    return payload


@router.post("/uc01/ladder")
def uc01_ladder(req: LadderRequest) -> dict[str, Any]:
    """Run the ladder for one contact as a job; identical calls of the record are reused."""
    check_provider(req.provider)
    cascade = _selected_judge(req.judge)
    try:
        lvls = levels.parse_levels(req.levels)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if any(lvl.uses_model for lvl in lvls):
        require_llm_calls_on(req.provider)
    if db_one("SELECT id FROM uc_contacts WHERE id = ?", (req.contact_id,)) is None:
        raise HTTPException(
            status_code=404, detail=f"contact_not_found: {req.contact_id}"
        )
    pick = _pick()
    reuse = [p.name for p in card.ladder_runs()]
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    run_id = (
        f"page-{stamp}-contact-{req.contact_id}-{req.provider}-{req.tier or 'default'}"
    )
    levels_spec = req.levels

    def target(progress: jobs.ProgressFn) -> dict[str, Any]:
        """Run the ladder, optionally judge the messages it produced, and summarize the folder."""
        folder = runner.run(
            pick,
            levels_spec=levels_spec,
            contacts=[req.contact_id],
            provider=req.provider,
            model=req.model,
            tier=req.tier,
            judges=("rules",),
            run_id=run_id,
            reuse=reuse,
            progress=lambda done, total: progress(done, total),
        )
        summary = read_json(folder / "config.json", {}) or {}
        message_rows = judge_run.load_run_messages(folder)
        judgment = None
        if cascade:
            if message_rows:
                judged = judge_run.judge_run(
                    folder.name,
                    cascade,
                    runs_dir=folder.parent,
                    judge_id=f"judge-page-{uuid.uuid4().hex[:12]}",
                    contacts=[req.contact_id],
                )
                judgment = {
                    "folder": f"{folder.name}/{judged.name}",
                    "config": read_json(judged / "config.json", {}),
                    "summary": read_json(judged / "summary.json", {}),
                    "rows": [
                        json.loads(line)
                        for line in read_text(judged / "verdicts.jsonl").splitlines()
                        if line.strip()
                    ],
                }
            else:
                judgment = {"skipped": "No generated messages to judge"}
        return {
            "run_dir": folder.name,
            "messages": summary.get("messages"),
            "llm_calls": summary.get("llm_calls"),
            "reused": summary.get("reused"),
            "seconds": summary.get("seconds"),
            "judgment": judgment,
            "rows": message_rows,
        }

    job = jobs.start(
        "uc01-ladder",
        f"UC-01 žebřík · kontakt {req.contact_id} · {req.provider} · úrovně {req.levels}",
        target,
    )
    return {"job": job.to_dict(), "run_id": run_id, "reuse": reuse}


# ---------------------------------------------------------------------------
# Run folders and the card
# ---------------------------------------------------------------------------


def _run_kind(name: str, config: dict[str, Any]) -> str:
    """Classify a run folder as ``faithfulness``, ``ocean``, ``smoke``, ``page`` or ``ladder``."""
    if config.get("kind") == "faithfulness":
        return "faithfulness"
    if "ocean-inference" in name:
        return "ocean"
    if name.startswith("smoke"):
        return "smoke"
    if name.startswith("page-"):
        return "page"
    return "ladder"


@router.get("/uc01/runs")
def uc01_runs() -> dict[str, Any]:
    """Every run folder under ``snapshots/runs/`` with its configuration in short."""
    records = {p.name for p in card.ladder_runs()}
    record_name = max(records) if records else None
    runs = []
    for folder in run_folders(UC01_RUNS_DIR):
        cfg = read_json(folder / "config.json", {}) or {}
        runs.append(
            {
                "name": folder.name,
                "kind": _run_kind(folder.name, cfg),
                "record": folder.name == record_name,
                "created": cfg.get("created"),
                "provider": cfg.get("provider"),
                "model": cfg.get("model"),
                "tier": cfg.get("tier"),
                "levels": cfg.get("levels"),
                "contacts": cfg.get("contacts"),
                "briefs": cfg.get("briefs"),
                "messages": cfg.get("messages"),
                "llm_calls": cfg.get("llm_calls"),
                "reused": cfg.get("reused"),
                "seconds": cfg.get("seconds"),
                "has_messages": (folder / "messages.jsonl").exists(),
                "has_summary": (folder / "summary.json").exists(),
            }
        )
    return {"runs": runs, "record": record_name, "source": str(UC01_RUNS_DIR)}


@router.get("/uc01/runs/{run_id}/messages")
def uc01_run_messages(
    run_id: str,
    contact: int | None = None,
    level: str | None = None,
    brief: int | None = None,
    prompts: bool = False,
    limit: int = 300,
) -> dict[str, Any]:
    """Rows of a run's ``messages.jsonl`` filtered by contact, level and brief."""
    folder = folder_or_404(UC01_RUNS_DIR, run_id)
    path = folder / "messages.jsonl"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no messages.jsonl in {run_id}")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if contact is not None and int(row.get("contact_id", -1)) != contact:
                continue
            if level is not None and str(row.get("level")) != level:
                continue
            if brief is not None and int(row.get("brief_id", -1)) != brief:
                continue
            if not prompts:
                row.pop("system_prompt", None)
                row.pop("user_prompt", None)
            rows.append(row)
            if len(rows) >= limit:
                break
    summary = read_json(folder / "summary.json", None)
    return {
        "run": run_id,
        "rows": rows,
        "summary": summary,
        "config": read_json(folder / "config.json", {}),
    }


@router.get("/uc01/results")
def uc01_results() -> dict[str, Any]:
    """The one-page card of the run of record and the picks."""
    pick = _pick()
    return {
        "card": read_text(UC01_DIR / "eval" / "RESULTS.md"),
        "pick": {
            "name": pick.get("name"),
            "created": pick.get("created"),
            "rule": pick.get("rule"),
            "reading_set": pick.get("reading_set"),
            "strata": pick.get("strata"),
            "briefs": pick.get("briefs"),
            "brief_titles": pick.get("brief_titles"),
        },
        "source": str(UC01_DIR / "eval"),
    }
