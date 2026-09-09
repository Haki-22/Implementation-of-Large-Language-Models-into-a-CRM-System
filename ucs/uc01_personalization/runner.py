"""The runner: loop a pick over briefs and levels, one folder per run.

Nothing here decides anything. It reads a pick, calls ``generate()`` for every
(contact, level, brief) the pick's ``briefs_by_level`` map asks for (an explicit
``--briefs`` list overrides it for every level), and writes the run to
``snapshots/runs/<run-id>/``:

    config.json     what ran: pick name, levels, briefs per level, provider and the
                    RESOLVED model/tier (a default run says "gpt-5.6-luna", not null;
                    the raw arguments sit under "requested"), judges, prompt
                    version, the LLM-switch state, the database sha256, reuse, timing
    pick.json       a copy of the pick used, so the run is self-contained
    messages.jsonl  one ``Generation`` per line (prompts included)
    results.csv     one flat row per message for tables and charts
    summary.json    per level: generated, skipped (by reason), errors, rules
                    acceptance; the model judges write their own judge-<id>/
                    beside these files (judge_run.py)

A run is the provenance of a number in the thesis; runs are never edited, a
correction is a new run.
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ucs.uc01_personalization import data, levels, prompts
from ucs.uc01_personalization.generate import Generation, generate
from utils.generation import resolve_model, resolve_tier
from utils.llm_switch import llm_calls_source
from utils.hashing import file_sha256
from utils.paths import SUBSTRATE_DB, UC01_RUNS_DIR

DEFAULT_CONCURRENCY = 4

RESULT_COLUMNS = (
    "run_id",
    "contact_id",
    "brief_id",
    "level",
    "level_name",
    "stratum",
    "gender",
    "formal",
    "gender_paired",
    "ocean_source",
    "lifecycle_stage",
    "used_model",
    "provider",
    "model",
    "tier",
    "reused_from",
    "ok",
    "skipped",
    "error",
    "rules_accepted",
    "rules_failures",
    "rules_unchecked",
    "seconds",
    "chars",
)


# ---------------------------------------------------------------------------
# Run id and folder
# ---------------------------------------------------------------------------


def make_run_id(pick_name: str, provider: str, levels_spec: str) -> str:
    """Default run id: UTC stamp, pick name, provider and levels, slugged."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    slug = re.sub(r"[^a-z0-9]+", "-", f"{pick_name}-{provider}-{levels_spec}".lower()).strip("-")
    return f"{stamp}-{slug}"


def run_dir(run_id: str) -> Path:
    """The folder of a run under ``snapshots/runs/``."""
    return UC01_RUNS_DIR / run_id


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def _stratum(pick: dict[str, Any], contact_id: int) -> str:
    """The contact's data tier from the pick (full / partial / prospect / defective), else 'extra'."""
    facts = pick.get("contacts", {}).get(str(contact_id))
    if facts and facts.get("tier"):
        return facts["tier"]
    for name, ids in pick.get("strata", {}).items():
        if contact_id in ids:
            return name
    return "reading" if contact_id in pick.get("reading_set", []) else "extra"


def load_reuse(
    run_ids: list[str], runs_dir: Path | None = None
) -> dict[tuple[int, int, str], dict]:
    """(contact, brief, level) -> the newest ok row of the named earlier runs, each row tagged with its run id.

    A run id is a folder under ``runs_dir`` (default ``snapshots/runs/``) or a path.
    Later ids win over earlier ones for the same key; whether a row is really taken
    over is decided per job by ``generate.reusable`` (identical inputs).
    """
    index: dict[tuple[int, int, str], dict] = {}
    for run_id in run_ids:
        folder = Path(run_id) if Path(run_id).is_dir() else (runs_dir or UC01_RUNS_DIR) / run_id
        path = folder / "messages.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"--reuse {run_id}: no messages.jsonl under {folder}")
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                if row.get("ok") and row.get("used_model"):
                    key = (int(row["contact_id"]), int(row["brief_id"]), str(row["level"]))
                    index[key] = {**row, "run_id": folder.name}
    return index


async def _run_async(
    jobs: list[tuple[int, int, levels.Level]],
    *,
    provider: str,
    model: str | None,
    tier: str | None,
    judges: tuple[str, ...],
    concurrency: int,
    reuse_index: dict[tuple[int, int, str], dict] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[Generation]:
    """Run every (contact, brief, level) job concurrently under one connection and a semaphore.

    ``reuse_index`` (see ``load_reuse``) lets each job copy an earlier identical
    call instead of dispatching one; ``progress`` is called after each job
    completes with (done, total).
    """
    sem = asyncio.Semaphore(concurrency)
    conn = data.connect()
    done = 0

    async def one(cid: int, bid: int, lvl: levels.Level) -> Generation:
        """Generate one job's message, reusing the matching stored row when one exists."""
        nonlocal done
        stored = reuse_index.get((cid, bid, lvl.id)) if reuse_index else None
        async with sem:
            gen = await generate(
                cid,
                bid,
                lvl,
                provider=provider,
                model=model,
                tier=tier,
                judges=judges,
                conn=conn,
                reuse=stored,
            )
        done += 1
        if progress is not None:
            progress(done, len(jobs))
        return gen

    try:
        return await asyncio.gather(*(one(cid, bid, lvl) for cid, bid, lvl in jobs))
    finally:
        conn.close()


def _row(run_id: str, pick: dict[str, Any], g: Generation) -> dict[str, Any]:
    """One ``results.csv`` row for a generation: its facts, outcome and rules verdict, flattened."""
    return {
        "run_id": run_id,
        "contact_id": g.contact_id,
        "brief_id": g.brief_id,
        "level": g.level,
        "level_name": g.level_name,
        "stratum": _stratum(pick, g.contact_id),
        "gender": g.gender,
        "formal": g.formal,
        "gender_paired": int(g.gender_paired),
        "ocean_source": g.ocean_source,
        "lifecycle_stage": g.lifecycle_stage,
        "used_model": int(g.used_model),
        "provider": g.provider,
        "model": g.model,
        "tier": g.tier,
        "reused_from": g.reused_from or "",
        "ok": int(g.ok),
        "skipped": ",".join(g.skipped),
        "error": g.error or "",
        "rules_accepted": "" if g.rules is None else int(g.rules["accepted"]),
        "rules_failures": "" if g.rules is None else ",".join(g.rules["failures"]),
        "rules_unchecked": "" if g.rules is None else ",".join(g.rules.get("unchecked", [])),
        "seconds": g.seconds,
        "chars": len(g.text) if g.text else 0,
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per level: how many ran, were skipped (by reason) or failed, and the acceptance rates."""
    out: dict[str, Any] = {}
    for level in levels.LADDER:
        mine = [r for r in rows if r["level"] == level]
        if not mine:
            continue
        ok = [r for r in mine if r["ok"]]
        ruled = [r for r in ok if r["rules_accepted"] != ""]
        out[level] = {
            "name": mine[0]["level_name"],
            "requested": len(mine),
            "generated": len(ok),
            "skipped": dict(Counter(r["skipped"] for r in mine if r["skipped"])),
            "errors": sum(1 for r in mine if r["error"]),
            "reused": sum(1 for r in ok if r.get("reused_from")),
            "rules_accepted": sum(r["rules_accepted"] for r in ruled),
            "rules_rate": round(sum(r["rules_accepted"] for r in ruled) / len(ruled), 3)
            if ruled
            else None,
            "rules_failures": dict(
                Counter(f for r in ruled for f in r["rules_failures"].split(",") if f)
            ),
            # checks that could not apply because the row lacks the field (defective rows)
            "rules_unchecked": dict(
                Counter(u for r in ruled for u in r["rules_unchecked"].split(",") if u)
            ),
            "seconds_total": round(sum(r["seconds"] for r in ok), 1),
        }
    return out


def run(
    pick: dict[str, Any],
    *,
    levels_spec: str = "all",
    briefs: list[int] | None = None,
    contacts: list[int] | None = None,
    provider: str = "mock",
    model: str | None = None,
    tier: str | None = "low",
    judges: tuple[str, ...] = ("rules",),
    concurrency: int = DEFAULT_CONCURRENCY,
    run_id: str | None = None,
    runs_dir: Path | None = None,
    reuse: list[str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Run the pick (or a subset) over the levels; return the run folder.

    ``runs_dir`` defaults to ``snapshots/runs/``; tests pass a temporary directory.
    ``reuse`` names earlier run folders whose identical calls are copied instead of
    sent again (``load_reuse`` + ``generate.reusable``): a smoke on one contact becomes
    part of the run of record, and a rerun after failures re-sends only what failed.
    ``progress(done, total)`` is called after every generated message (the demo page
    shows it); ``None`` is silent.
    """
    lvls = levels.parse_levels(levels_spec)
    contact_ids = contacts or (
        pick["reading_set"] + [i for ids in pick["strata"].values() for i in ids]
    )
    # Which briefs each level runs on: an explicit list wins for every level, else the
    # pick's map (D-UC01-3); a pick written before the map ran every level on all briefs.
    by_level = pick.get("briefs_by_level") or {}
    briefs_for = {
        lvl.id: list(briefs) if briefs else [int(b) for b in by_level.get(lvl.id, pick["briefs"])]
        for lvl in lvls
    }
    brief_ids = sorted({b for ids in briefs_for.values() for b in ids})
    jobs = [(cid, bid, lvl) for cid in contact_ids for lvl in lvls for bid in briefs_for[lvl.id]]
    rid = run_id or make_run_id(pick["name"], provider, levels_spec.replace(",", "-"))
    folder = (runs_dir or UC01_RUNS_DIR) / rid
    if folder.exists():
        raise FileExistsError(f"run folder exists, a run is never overwritten: {folder}")
    folder.mkdir(parents=True)

    enabled, source = llm_calls_source()
    reuse_index = load_reuse(list(reuse), runs_dir) if reuse else None
    started = time.monotonic()
    gens = asyncio.run(
        _run_async(
            jobs,
            provider=provider,
            model=model,
            tier=tier,
            judges=judges,
            concurrency=concurrency,
            reuse_index=reuse_index,
            progress=progress,
        )
    )
    rows = [_row(rid, pick, g) for g in gens]
    summary = summarise(rows)

    (folder / "pick.json").write_text(
        json.dumps(pick, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (folder / "messages.jsonl").open("w", encoding="utf-8") as fh:
        for g in gens:
            fh.write(json.dumps(g.to_dict(), ensure_ascii=False) + "\n")
    with (folder / "results.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    config = {
        "run_id": rid,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pick": pick["name"],
        "contacts": contact_ids,
        "briefs": brief_ids,
        "briefs_by_level": briefs_for,
        "levels": [lvl.id for lvl in lvls],
        "provider": provider,
        "model": resolve_model(provider, model),
        "tier": resolve_tier(provider, tier, model),
        "requested": {"model": model, "tier": tier},
        "judges": list(judges),
        "prompt_version": prompts.PROMPT_VERSION,
        "llm_calls": {"enabled": enabled, "source": source},
        "database": {"path": str(SUBSTRATE_DB), "sha256": file_sha256(SUBSTRATE_DB)},
        "reuse": list(reuse) if reuse else [],
        "reused": sum(1 for g in gens if g.reused_from),
        "concurrency": concurrency,
        "seconds": round(time.monotonic() - started, 1),
        "messages": len(gens),
    }
    (folder / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (folder / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return folder
