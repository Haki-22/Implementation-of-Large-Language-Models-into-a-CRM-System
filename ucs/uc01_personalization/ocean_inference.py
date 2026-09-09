"""Infer contacts' OCEAN (Big Five) profiles from their English reviews with a model, into a run folder; freeze a run into the committed snapshot.

For every targeted contact the model reads a capped sample of the contact's
**English** review texts from ``uc_reviews`` (English, because the Czech text is
a machine translation and inference from it would measure the translator; user
decision 2026-09-04) and estimates the five BFI-2 traits on a 1-5 scale with one
verbatim evidence quote per trait. The answer arrives through the provider's
structured-output flag against ``SCHEMA``; a profile outside the range is a
failed call, never a silently clipped number.

Who is targeted is a composition of rules, never a hand-made list (decision of
2026-09-06): ``--sample`` = UC-04's fixed customer sample (the people the model
arms run on), ``--pick`` = the linked contacts of UC-01's pick (the people whose
messages the reading pass looks at), ``--previous`` = everyone who carries an
inferred profile in the committed snapshot today (so a rerun with one provider
leaves nobody worse off), ``--contacts`` / ``--all`` for by-hand or census runs.
``--limit N`` takes the first N targets by contact id, the measurement batch
before a full run; ``--exclude-runs`` drops the targets an earlier run folder
already holds a profile for, so a batch continues where the last one stopped and
``freeze`` merges the folders.

A run writes ``snapshots/runs/<date>-ocean-inference-<provider>-<model>-<tier>-<N>-contacts/``:
``config.json`` (provider, resolved model and tier, the provider CLI's version,
prompt version and text, schema, caps, database hash), ``targets.json`` (who and by which rule),
``responses/<reviewer>.json`` (the verbatim prompt, the raw answer, the parsed
profile or the error; written as each call returns), ``status.csv`` (one row per
target: ok / failed / skipped, seconds), ``profiles.json`` (the profiles in the
snapshot's shape), ``summary.json`` and the one-page ``RESULTS.md``. A run folder
is the provenance of a profile and is never edited.

``freeze`` rewrites the committed snapshot ``snapshots/ocean_inferred.json`` from
one or more run folders (keyed by reviewer id; each entry names its run). The
database build loads the five numbers into ``Contact.ocean`` with
``ocean_source = 'inferred'``; the quotes stay in the snapshot as evidence. A
freeze that would drop reviewers present today refuses unless ``--replace`` is
given, and the old file then belongs under ``substrate/snapshots/provenance/`` as
the record of its run.

``attachment`` writes the appendix pair ``<project_root>/attachments/ocean-inference.{csv,md}``
from the run folders the snapshot names (the project's own appendix convention: an
appendix always quotes a generated file, never a typed number): one row per run, the
trait means per group, and the agreement with the May 2026 record kept under
``substrate/snapshots/provenance/``.

One call per contact, behind the ``THESIS_LLM_CALLS`` switch (``--force-llm``).

Run:
    python -m ucs.uc01_personalization.ocean_inference infer --sample model-arms-100 --pick uc01-personalization-20-level --previous --provider mock
    python -m ucs.uc01_personalization.ocean_inference infer --sample model-arms-100 --pick uc01-personalization-20-level --previous --limit 20 --provider agy --model gemini-3.8-flash --tier medium --force-llm
    python -m ucs.uc01_personalization.ocean_inference infer --sample model-arms-100 --pick uc01-personalization-20-level --previous --exclude-runs <run-id> --provider agy --model gemini-3.8-flash --tier medium --force-llm
    python -m ucs.uc01_personalization.ocean_inference freeze --runs <run-id>[,<run-id>] [--replace]
    python -m ucs.uc01_personalization.ocean_inference attachment            # <project_root>/attachments/ocean-inference.{csv,md}
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as _dt
import json
import logging
import re
import sqlite3
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ucs.uc01_personalization import data, picker
from ucs.uc02_pseudonymization.eval.runs import (
    code_identity,
    file_sha256,
    format_duration,
    new_run_dir,
    write_card,
    write_json,
)
from utils.generation import PROVIDERS, cli_version, generate_json, resolve_model, resolve_tier
from utils.llm_switch import add_force_llm_argument, apply_force_llm
from utils.paths import (
    OCEAN_INFERRED_SNAPSHOT,
    PROVENANCE_DIR,
    SUBSTRATE_DB,
    THESIS_ROOT,
    UC01_RUNS_DIR,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONCURRENCY = 4
MAX_REVIEWS_PER_CONTACT = 15  # the most helpful, then most recent; caps the prompt
MAX_REVIEW_CHARS = 600  # per review
TIMEOUT_SECONDS = 180
TRAITS = ("O", "C", "E", "A", "N")
# 1.0.0 = the May run (Gemini 3.1 Pro, reviews from the JSON snapshot); 1.1.0 read the
# reviews from the database, same wording; 1.2.0 = same wording, the answer through the
# provider's structured-output flag, one run folder per batch.
PROMPT_VERSION = "1.2.0"

SYSTEM_PROMPT = (
    "You are an experienced psychometrician applying the Big Five Inventory 2 "
    "(BFI-2; Soto & John 2017) framework. You receive an anonymized customer's "
    "Amazon review history. Estimate the customer's Big Five personality "
    "scores on a 1.00-5.00 scale (continuous, two decimals) using textual "
    "evidence ONLY from the reviews. Each dimension must come with a short "
    "verbatim evidence quote (<= 30 words) extracted from the reviews that "
    "supports your estimate.\n\n"
    "Dimensions:\n"
    "- O Openness to Experience (intellectual curiosity, aesthetic sensitivity)\n"
    "- C Conscientiousness (organization, dependability, attention to detail)\n"
    "- E Extraversion (sociability, assertiveness, positive emotion)\n"
    "- A Agreeableness (warmth, trust, cooperation)\n"
    "- N Neuroticism (negative emotionality, anxiety, frustration sensitivity)\n\n"
    "Calibrate against US population means (O=3.75, C=3.55, E=3.20, A=3.75, N=2.85). "
    "Avoid extreme scores unless strongly justified.\n\n"
    'Output strict JSON: {"O": <float>, "C": <float>, "E": <float>, "A": <float>, '
    '"N": <float>, "evidence_quotes": {"O": "...", "C": "...", "E": "...", '
    '"A": "...", "N": "..."}}'
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **{trait: {"type": "number", "minimum": 1.0, "maximum": 5.0} for trait in TRAITS},
        "evidence_quotes": {
            "type": "object",
            "properties": {trait: {"type": "string"} for trait in TRAITS},
            "required": list(TRAITS),
            "additionalProperties": False,
        },
    },
    "required": [*TRAITS, "evidence_quotes"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Targets: who gets a profile, by which rule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """One contact to infer for, with the rules that selected it."""

    contact_id: int
    reviewer_id: str | None
    group: str | None
    sources: tuple[str, ...]


def compose_targets(
    conn: sqlite3.Connection,
    *,
    pick: dict[str, Any] | None = None,
    sample: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
    contacts: list[int] | None = None,
    everyone: bool = False,
) -> tuple[list[Target], list[str]]:
    """The union of the selected rules as targets ordered by contact id, plus the reviewer ids of ``previous`` that no contact owns."""
    rows = {
        row["id"]: row
        for row in conn.execute("SELECT id, reviewer_id, amazon_group FROM uc_contacts")
    }
    by_reviewer = {row["reviewer_id"]: cid for cid, row in rows.items() if row["reviewer_id"]}
    sources: dict[int, list[str]] = {}

    def add(cid: int, source: str) -> None:
        """Record ``source`` as one reason ``cid`` was targeted, after checking it exists."""
        if cid not in rows:
            raise LookupError(f"contact {cid} is not in the database")
        sources.setdefault(cid, [])
        if source not in sources[cid]:
            sources[cid].append(source)

    if sample:
        for cid in sample["contact_ids"]:
            add(int(cid), f"sample:{sample['name']}")
    if pick:
        for cid, facts in pick.get("contacts", {}).items():
            if facts.get("amazon_group"):  # prospects have no reviews to read
                add(int(cid), f"pick:{pick['name']}")
    unmatched: list[str] = []
    if previous:
        for rid in previous:
            cid = by_reviewer.get(rid)
            if cid is None:
                unmatched.append(rid)
            else:
                add(cid, "previous")
    for cid in contacts or []:
        add(cid, "contacts")
    if everyone:
        for cid, row in rows.items():
            if row["reviewer_id"]:
                add(cid, "all")

    targets = [
        Target(cid, rows[cid]["reviewer_id"], rows[cid]["amazon_group"], tuple(sources[cid]))
        for cid in sorted(sources)
    ]
    return targets, unmatched


# ---------------------------------------------------------------------------
# Input: the contact's English reviews from the database
# ---------------------------------------------------------------------------


def review_block(conn: sqlite3.Connection, contact_id: int) -> tuple[str, int, int]:
    """The most helpful, then most recent reviews of the contact, capped; the text, how many were used, how many exist."""
    rows = conn.execute(
        """SELECT rating, summary_en, text_en FROM uc_reviews WHERE contact_id = ?
           ORDER BY helpful_up DESC, review_date DESC, id LIMIT ?""",
        (contact_id, MAX_REVIEWS_PER_CONTACT),
    ).fetchall()
    total = conn.execute(
        "SELECT count(*) FROM uc_reviews WHERE contact_id = ?", (contact_id,)
    ).fetchone()[0]
    lines = []
    for r in rows:
        summary = (r["summary_en"] or "").strip().replace("\n", " ")
        text = (r["text_en"] or "").strip().replace("\n", " ")[:MAX_REVIEW_CHARS]
        lines.append(f"[*{r['rating']}] {summary}: {text}")
    return "\n\n".join(lines), len(rows), total


def build_prompt(contact_id: int, block: str, used: int, total: int) -> str:
    """The user turn: the anonymised id, the capped review sample, the instruction."""
    return (
        f"Customer ID: {contact_id} (anonymized).\n"
        f"Review sample ({used} of {total} reviews shown, sorted by helpfulness):\n\n"
        f"{block}\n\nEstimate BFI-2 personality dimensions. Return JSON only."
    )


# ---------------------------------------------------------------------------
# Output: validation
# ---------------------------------------------------------------------------


def validate_profile(obj: Any) -> dict[str, Any]:
    """The five traits as floats inside [1, 5] (two decimals) plus one quote per trait.

    Raises:
        ValueError: a trait is missing, not a number, or outside the BFI range.
    """
    if not isinstance(obj, dict):
        raise ValueError(f"expected an object, got {type(obj).__name__}")
    profile: dict[str, Any] = {}
    for trait in TRAITS:
        try:
            value = float(obj[trait])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"trait {trait} missing or not a number") from exc
        if not 1.0 <= value <= 5.0:
            raise ValueError(f"trait {trait}={value} outside [1, 5]")
        profile[trait] = round(value, 2)
    quotes = obj.get("evidence_quotes") or {}
    if not isinstance(quotes, dict):
        raise ValueError("evidence_quotes is not an object")
    profile["evidence_quotes"] = {trait: str(quotes.get(trait) or "") for trait in TRAITS}
    return profile


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@dataclass
class CallRecord:
    """What one target produced: the status, the timing, the profile or the error."""

    contact_id: int
    reviewer_id: str | None
    group: str | None
    sources: str
    reviews_total: int
    reviews_used: int
    prompt_chars: int
    status: str  # ok | failed | skipped
    seconds: float
    error: str
    profile: dict[str, Any] | None


async def infer_one(
    conn: sqlite3.Connection,
    target: Target,
    *,
    provider: str,
    model: str | None,
    tier: str | None,
    sem: asyncio.Semaphore,
    responses_dir: Path,
) -> CallRecord:
    """One target: build the prompt, one model call, validate, write the response file at once."""
    sources = "+".join(target.sources)
    if not target.reviewer_id:
        return CallRecord(
            target.contact_id,
            None,
            target.group,
            sources,
            0,
            0,
            0,
            "skipped",
            0.0,
            "prospect (no reviewer)",
            None,
        )
    block, used, total = review_block(conn, target.contact_id)
    if not used:
        return CallRecord(
            target.contact_id,
            target.reviewer_id,
            target.group,
            sources,
            total,
            0,
            0,
            "skipped",
            0.0,
            "no reviews",
            None,
        )
    prompt = build_prompt(target.contact_id, block, used, total)
    raw: Any = None
    error = ""
    profile: dict[str, Any] | None = None
    seconds = 0.0
    async with sem:
        t0 = time.perf_counter()  # the call itself, not the wait for a slot
        try:
            raw = await generate_json(
                prompt,
                SCHEMA,
                provider=provider,
                system_prompt=SYSTEM_PROMPT,
                model=model,
                tier=tier,
                timeout=TIMEOUT_SECONDS,
            )
            profile = validate_profile(raw)
        except Exception as exc:  # noqa: BLE001 - one failed call is a row, not a crash
            error = f"{type(exc).__name__}: {exc}"[:500]
            logger.warning("OCEAN inference failed for contact %s: %s", target.contact_id, error)
        seconds = round(time.perf_counter() - t0, 2)
    record = CallRecord(
        target.contact_id,
        target.reviewer_id,
        target.group,
        sources,
        total,
        used,
        len(prompt),
        "ok" if profile else "failed",
        seconds,
        error,
        profile,
    )
    write_json(
        responses_dir / f"{target.reviewer_id}.json",
        {**asdict(record), "prompt": prompt, "system_prompt": SYSTEM_PROMPT, "raw": raw},
    )
    return record


async def infer_all(
    conn: sqlite3.Connection,
    targets: list[Target],
    *,
    provider: str,
    model: str | None,
    tier: str | None,
    concurrency: int,
    responses_dir: Path,
) -> list[CallRecord]:
    """Run ``infer_one`` for every target concurrently under a semaphore; one ``CallRecord`` each, target order."""
    sem = asyncio.Semaphore(concurrency)
    return list(
        await asyncio.gather(
            *(
                infer_one(
                    conn,
                    t,
                    provider=provider,
                    model=model,
                    tier=tier,
                    sem=sem,
                    responses_dir=responses_dir,
                )
                for t in targets
            )
        )
    )


# ---------------------------------------------------------------------------
# A run: folder, config, status, profiles, card
# ---------------------------------------------------------------------------


def _profile_entry(record: CallRecord, config: dict[str, Any]) -> dict[str, Any]:
    """One snapshot entry: the numbers, the quotes, and where they came from."""
    assert record.profile is not None
    return {
        **record.profile,
        "group": record.group,
        "_contact_id": record.contact_id,
        "_reviews": record.reviews_total,
        "_reviews_used": record.reviews_used,
        "_provider": config["provider"],
        "_model": config["model"],
        "_tier": config["tier"],
        "_prompt_version": config["prompt_version"],
        "_date": config["date"],
        "_run": config["run_dir"],
    }


def _summary(records: list[CallRecord], seconds: float) -> dict[str, Any]:
    """Aggregate a run's ``CallRecord``s: counts by status, call timing, and per-trait mean/sd/min/max."""
    ok = [r for r in records if r.status == "ok"]
    call_seconds = [r.seconds for r in records if r.status != "skipped"]
    traits: dict[str, dict[str, float]] = {}
    for trait in TRAITS:
        values = [r.profile[trait] for r in ok]  # type: ignore[index]
        if values:
            traits[trait] = {
                "mean": round(statistics.fmean(values), 2),
                "sd": round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
                "min": min(values),
                "max": max(values),
            }
    groups = sorted({r.group or "?" for r in records})
    return {
        "targets": len(records),
        "ok": len(ok),
        "failed": sum(1 for r in records if r.status == "failed"),
        "skipped": sum(1 for r in records if r.status == "skipped"),
        "wall_seconds": round(seconds, 1),
        "median_call_seconds": round(statistics.median(call_seconds), 1) if call_seconds else None,
        "max_call_seconds": max(call_seconds) if call_seconds else None,
        "median_prompt_chars": int(
            statistics.median(r.prompt_chars for r in records if r.prompt_chars)
        )
        if any(r.prompt_chars for r in records)
        else None,
        "by_group": {
            g: {
                "targets": sum(1 for r in records if (r.group or "?") == g),
                "ok": sum(1 for r in ok if (r.group or "?") == g),
            }
            for g in groups
        },
        "traits": traits,
    }


def _write_status(run_dir: Path, records: list[CallRecord]) -> None:
    """Write ``status.csv``, one row per target, from the listed ``CallRecord`` fields."""
    fields = [
        "contact_id",
        "reviewer_id",
        "group",
        "sources",
        "reviews_total",
        "reviews_used",
        "prompt_chars",
        "status",
        "seconds",
        "error",
    ]
    with open(run_dir / "status.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k: getattr(r, k) for k in fields})


def _write_card_for(run_dir: Path, config: dict[str, Any], summary: dict[str, Any]) -> None:
    """Write the run's one-page card (``RESULTS.md``) from its config and summary."""
    rule = config["targets"]
    header = [
        ("Date", config["date"]),
        ("Provider / model / tier", f"{config['provider']} / {config['model']} / {config['tier']}"),
        (
            "Prompt",
            f"version {config['prompt_version']}, BFI-2 wording, {config['max_reviews_per_contact']} reviews x {config['max_review_chars']} chars at most",
        ),
        ("Targets", "; ".join(f"{k} = {v}" for k, v in rule.items() if v not in (None, False, []))),
        ("Database", f"{config['database']['file']} sha256 {config['database']['sha256'][:12]}"),
        ("Run folder", config["run_dir"]),
    ]
    calls = [
        (
            f"{summary['ok']} of {summary['targets']} profiles",
            "one call per contact; ok = a schema-valid profile inside 1-5",
        ),
        (
            f"{summary['failed']} failed",
            "provider error or a profile outside the range; the response file keeps the reason",
        ),
        (f"{summary['skipped']} skipped", "no reviews to read"),
        (
            format_duration(summary["wall_seconds"]),
            f"wall time at concurrency {config['concurrency']}",
        ),
    ]
    if summary["median_call_seconds"] is not None:
        calls.append(
            (
                f"{summary['median_call_seconds']} s median per call",
                f"the call itself, not the wait for a slot; max {summary['max_call_seconds']} s",
            )
        )
    if summary["median_prompt_chars"] is not None:
        calls.append(
            (f"{summary['median_prompt_chars']} chars median prompt", "review text the model saw")
        )
    who = [
        (f"{g}: {v['ok']} of {v['targets']}", "group of the substrate")
        for g, v in summary["by_group"].items()
    ]
    traits = [
        (f"{t} {v['mean']} +- {v['sd']}", f"min {v['min']}, max {v['max']}")
        for t, v in summary["traits"].items()
    ]
    write_card(
        run_dir,
        title=f"OCEAN inference: {summary['ok']} profiles from English reviews",
        header=header,
        blocks=[
            {"name": "Calls", "lines": calls},
            {"name": "By group", "lines": who},
            {
                "name": "Profiles (mean +- sd over the ok calls)",
                "lines": traits or [("no profiles", "")],
            },
        ],
        sentence=(
            f"{summary['ok']} of {summary['targets']} targeted contacts received a Big Five profile "
            f"estimated by {config['model']} from at most {config['max_reviews_per_contact']} of "
            "their English reviews. The profile is a reading of review text, not a measured "
            "personality; it enters the database only after `freeze` and a rebuild, with "
            "ocean_source = 'inferred' and this folder as its provenance."
        ),
    )


def profiled_reviewers(run_dirs: list[Path]) -> set[str]:
    """The reviewer ids that already hold a profile in the given run folders."""
    done: set[str] = set()
    for run_dir in run_dirs:
        done |= set(json.loads((run_dir / "profiles.json").read_text(encoding="utf-8")))
    return done


def run(
    *,
    provider: str,
    model: str | None = None,
    tier: str | None = None,
    pick_name: str | None = None,
    sample_name: str | None = None,
    previous: bool = False,
    contacts: list[int] | None = None,
    everyone: bool = False,
    limit: int | None = None,
    exclude_runs: list[Path] | None = None,
    concurrency: int = CONCURRENCY,
    db_path: Path = SUBSTRATE_DB,
    base_dir: Path = UC01_RUNS_DIR,
    snapshot: Path = OCEAN_INFERRED_SNAPSHOT,
    label: str | None = None,
) -> Path:
    """Infer for the composed targets into a new run folder; returns the folder."""
    pick = picker.load_pick(pick_name) if pick_name else None
    sample = None
    if sample_name:
        from ucs.uc04_matchmaker.sample import load_sample  # the model arms' sample (UC-04)

        sample = load_sample(sample_name)
    previous_file = (
        json.loads(snapshot.read_text(encoding="utf-8")) if previous and snapshot.exists() else None
    )
    if previous and previous_file is None:
        logger.warning("--previous given but %s does not exist; nothing to carry over", snapshot)

    conn = data.connect(db_path)
    try:
        targets, unmatched = compose_targets(
            conn,
            pick=pick,
            sample=sample,
            previous=previous_file,
            contacts=contacts,
            everyone=everyone,
        )
        if not targets:
            raise LookupError("no targets: pass --sample, --pick, --previous, --contacts or --all")
        already = profiled_reviewers(exclude_runs or [])
        excluded = [t for t in targets if t.reviewer_id in already]
        targets = [t for t in targets if t.reviewer_id not in already]
        if not targets:
            raise LookupError("every target already has a profile in the excluded runs")
        if limit is not None:
            targets = targets[:limit]
        for rid in unmatched:
            logger.warning(
                "previous profile %s belongs to no contact in the database; dropped", rid
            )

        resolved_model = resolve_model(provider, model)
        resolved_tier = resolve_tier(provider, tier, model)
        tag = label or (
            f"ocean-inference-{provider}-{resolved_model}-{resolved_tier or 'notier'}-{len(targets)}-contacts"
        )
        run_dir = new_run_dir(tag, base=base_dir)
        responses_dir = run_dir / "responses"
        responses_dir.mkdir()
        config: dict[str, Any] = {
            "run_dir": run_dir.name,
            "date": _dt.date.today().isoformat(),
            "provider": provider,
            "model": resolved_model,
            "tier": resolved_tier,
            "provider_cli_version": cli_version(provider),
            "prompt_version": PROMPT_VERSION,
            "system_prompt": SYSTEM_PROMPT,
            "schema": SCHEMA,
            "max_reviews_per_contact": MAX_REVIEWS_PER_CONTACT,
            "max_review_chars": MAX_REVIEW_CHARS,
            "review_order": "helpful_up DESC, review_date DESC, id",
            "language": "English reviews only (the Czech text is a machine translation)",
            "concurrency": concurrency,
            "timeout_seconds": TIMEOUT_SECONDS,
            "targets": {
                "sample": sample_name,
                "pick": pick_name,
                "previous": f"{snapshot.name} ({len(previous_file)} profiles)"
                if previous_file
                else None,
                "contacts": contacts or [],
                "all": everyone,
                "limit": limit,
                "exclude_runs": [r.name for r in exclude_runs or []],
                "excluded_count": len(excluded),
                "count": len(targets),
                "unmatched_previous": unmatched,
            },
            "database": {
                "file": str(db_path.relative_to(SUBSTRATE_DB.parents[2]))
                if db_path.is_relative_to(SUBSTRATE_DB.parents[2])
                else str(db_path),
                "sha256": file_sha256(db_path),
                "linked_contacts": conn.execute(
                    "SELECT count(*) FROM uc_contacts WHERE reviewer_id IS NOT NULL"
                ).fetchone()[0],
            },
            "code": code_identity(("numpy",)),
        }
        write_json(run_dir / "config.json", config)
        write_json(run_dir / "targets.json", [asdict(t) for t in targets])
        if sample:
            write_json(run_dir / "sample.json", sample)
        if pick:
            write_json(run_dir / "pick.json", pick)

        logger.info(
            "OCEAN inference for %d contacts (provider=%s, model=%s, tier=%s) -> %s",
            len(targets),
            provider,
            resolved_model,
            resolved_tier,
            run_dir.name,
        )
        t0 = time.perf_counter()
        records = asyncio.run(
            infer_all(
                conn,
                targets,
                provider=provider,
                model=model,
                tier=tier,
                concurrency=concurrency,
                responses_dir=responses_dir,
            )
        )
        seconds = time.perf_counter() - t0
    finally:
        conn.close()

    _write_status(run_dir, records)
    profiles = {r.reviewer_id: _profile_entry(r, config) for r in records if r.status == "ok"}
    write_json(run_dir / "profiles.json", profiles)
    summary = _summary(records, seconds)
    write_json(run_dir / "summary.json", summary)
    _write_card_for(run_dir, config, summary)
    return run_dir


# ---------------------------------------------------------------------------
# Freeze: run folders -> the committed snapshot
# ---------------------------------------------------------------------------


def freeze(
    run_dirs: list[Path], *, output: Path = OCEAN_INFERRED_SNAPSHOT, replace: bool = False
) -> tuple[Path, dict[str, int]]:
    """Rewrite the snapshot from the profiles of the given run folders; returns the path and counts.

    Raises:
        ValueError: a reviewer appears in more than one run folder.
        FileExistsError: the snapshot holds reviewers the runs do not, and ``replace`` is False.
    """
    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}
    for run_dir in run_dirs:
        profiles = json.loads((run_dir / "profiles.json").read_text(encoding="utf-8"))
        for rid, entry in profiles.items():
            if rid in merged:
                raise ValueError(
                    f"reviewer {rid} has a profile in both {origin[rid]} and {run_dir.name}; "
                    "freeze one run per reviewer"
                )
            merged[rid] = entry
            origin[rid] = run_dir.name
    existing = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    dropped = sorted(set(existing) - set(merged))
    if dropped and not replace:
        raise FileExistsError(
            f"{output.name} holds {len(dropped)} reviewers the runs do not "
            f"({', '.join(dropped[:5])}{', ...' if len(dropped) > 5 else ''}). Re-run with "
            "--replace to drop them, and move the old file under substrate/snapshots/provenance/ "
            "as the record of its run."
        )
    ordered = dict(sorted(merged.items(), key=lambda kv: kv[1].get("_contact_id", 0)))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output, {"profiles": len(ordered), "dropped": len(dropped), "runs": len(run_dirs)}


# ---------------------------------------------------------------------------
# Attachment: the appendix pair from the run folders the snapshot names
# ---------------------------------------------------------------------------

ATTACHMENTS_DIR = THESIS_ROOT / "attachments"
# The 2026-05-29 run (Gemini 3.1 Pro, 62 profiles) as the database read it until the
# 2026-09-06 rerun; kept as a record, compared against when present.
MAY_RECORD = PROVENANCE_DIR / "ocean-inference-2026-05-29" / "ocean_inferred-2026-05-29.json"
TRAIT_CS = {
    "O": "otevřenost",
    "C": "svědomitost",
    "E": "extraverze",
    "A": "přívětivost",
    "N": "neuroticismus",
}
Fact = tuple[str, str, Any, str]  # table, key, value, what it means


def _natural(name: str) -> list[Any]:
    """Sort key with numbers compared as numbers, so ``…-20-contacts`` precedes ``…-100-contacts``."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _display(path: Path) -> str:
    """``path`` relative to the project root when it lies inside, else its name."""
    try:
        return str(path.resolve().relative_to(THESIS_ROOT.resolve()))
    except ValueError:
        return path.name


def _mean_sd(values: list[float]) -> str:
    """``"mean ± population sd"`` to two decimals, or an em dash when ``values`` is empty."""
    if not values:
        return "–"
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    return f"{statistics.fmean(values):.2f} ± {sd:.2f}"


def attachment_facts(
    snapshot: Path = OCEAN_INFERRED_SNAPSHOT,
    base: Path = UC01_RUNS_DIR,
    may_record: Path = MAY_RECORD,
) -> tuple[list[Fact], list[str]]:
    """The appendix facts from the run folders the snapshot names; returns (facts, run folder names)."""
    profiles = json.loads(snapshot.read_text(encoding="utf-8"))
    run_names = sorted({entry["_run"] for entry in profiles.values()}, key=_natural)
    facts: list[Fact] = []
    for name in run_names:
        run_dir = base / name
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        wall = summary["wall_seconds"]
        per_minute = round(60 * (summary["ok"] + summary["failed"]) / wall, 1) if wall else None
        rows = [
            ("date", config["date"], "den běhu"),
            (
                "model",
                f"{config['provider']} / {config['model']} / {config['tier']}",
                "provider, model, úroveň uvažování",
            ),
            (
                "prompt_version",
                config["prompt_version"],
                "verze promptu (BFI-2, výstup vynucený schématem)",
            ),
            ("targets", summary["targets"], "cílených kontaktů"),
            ("ok", summary["ok"], "profilů uvnitř 1 až 5"),
            ("failed", summary["failed"], "selhaných volání"),
            ("skipped", summary["skipped"], "přeskočeno (bez recenzí)"),
            ("wall_seconds", wall, f"stěna při souběhu {config['concurrency']}"),
            ("calls_per_minute", per_minute, "propustnost"),
            (
                "median_prompt_chars",
                summary["median_prompt_chars"],
                "medián znaků recenzí v promptu",
            ),
            (
                "reviews_cap",
                f"{config['max_reviews_per_contact']} × {config['max_review_chars']}",
                "recenzí na kontakt × znaků na recenzi",
            ),
        ]
        facts += [(f"run:{name}", key, value, meaning) for key, value, meaning in rows]

    groups = sorted({entry["group"] for entry in profiles.values() if entry.get("group")})
    for group in [*groups, "all"]:
        members = [e for e in profiles.values() if group == "all" or e.get("group") == group]
        facts.append(
            (
                "profiles",
                f"{group}:n",
                len(members),
                "profilů ve skupině" if group != "all" else "profilů celkem",
            )
        )
        for trait in TRAITS:
            facts.append(
                (
                    "profiles",
                    f"{group}:{trait}",
                    _mean_sd([e[trait] for e in members]),
                    f"{TRAIT_CS[trait]}, průměr ± sd",
                )
            )

    if may_record.exists():
        may = json.loads(may_record.read_text(encoding="utf-8"))
        both = sorted(set(may) & set(profiles))
        facts.append(("may_2026", "overlap", len(both), "lidí s profilem v květnovém i novém běhu"))
        if both:
            for trait in TRAITS:
                diffs = [profiles[r][trait] - may[r][trait] for r in both]
                facts.append(
                    (
                        "may_2026",
                        f"{trait}:mean_abs_diff",
                        round(statistics.fmean(abs(d) for d in diffs), 2),
                        f"{TRAIT_CS[trait]}, průměrná absolutní odchylka nový − květen",
                    )
                )
                facts.append(
                    (
                        "may_2026",
                        f"{trait}:mean_diff",
                        round(statistics.fmean(diffs), 2),
                        f"{TRAIT_CS[trait]}, průměrná odchylka nový − květen (znaménko)",
                    )
                )
            facts.append(
                (
                    "may_2026",
                    "max_abs_diff",
                    round(max(abs(profiles[r][t] - may[r][t]) for r in both for t in TRAITS), 2),
                    "největší odchylka jednoho rysu",
                )
            )
    return facts, run_names


def attachment_markdown(facts: list[Fact], run_names: list[str], snapshot: Path) -> str:
    """Czech-captioned tables: one per run, the traits per group, the agreement with May."""
    lines = [
        "# Odvozený profil OCEAN (příloha, generováno)",
        "",
        f"Vygenerováno dne {_dt.date.today().isoformat()} ze složek běhů "
        + ", ".join(f"`ucs/uc01_personalization/snapshots/runs/{n}/`" for n in run_names)
        + f" a ze snímku `{_display(snapshot)}`, který je z nich zmrazen. "
        "Profil je odhad z textu anglických recenzí, ne změřená osobnost.",
        "",
    ]
    table_no = 0
    for name in run_names:
        table_no += 1
        lines += [
            f"Tabulka {table_no} – Běh `{name}`",
            "",
            "| klíč | hodnota | význam |",
            "| --- | --- | --- |",
        ]
        lines += [f"| `{k}` | {v} | {m} |" for t, k, v, m in facts if t == f"run:{name}"]
        lines.append("")
    table_no += 1
    groups = []
    for t, k, v, m in facts:
        if t == "profiles" and k.endswith(":n"):
            groups.append(k[:-2])
    lines += [
        f"Tabulka {table_no} – Rysy BFI-2 po skupinách (průměr ± sd na škále 1 až 5)",
        "",
        "| skupina | n | " + " | ".join(TRAIT_CS[t] for t in TRAITS) + " |",
        "| --- | --- | " + " | ".join("---" for _ in TRAITS) + " |",
    ]
    by_key = {(t, k): v for t, k, v, m in facts}
    for group in groups:
        label = "celkem" if group == "all" else group
        lines.append(
            f"| {label} | {by_key[('profiles', f'{group}:n')]} | "
            + " | ".join(str(by_key[("profiles", f"{group}:{t}")]) for t in TRAITS)
            + " |"
        )
    lines.append("")
    may_rows = [(k, v, m) for t, k, v, m in facts if t == "may_2026"]
    if may_rows:
        table_no += 1
        lines += [
            f"Tabulka {table_no} – Shoda s během z 29. 5. 2026 (Gemini 3.1 Pro) na společných lidech",
            "",
            "| klíč | hodnota | význam |",
            "| --- | --- | --- |",
        ]
        lines += [f"| `{k}` | {v} | {m} |" for k, v, m in may_rows]
        lines.append("")
    return "\n".join(lines)


def attachment_build(
    *,
    snapshot: Path = OCEAN_INFERRED_SNAPSHOT,
    base: Path = UC01_RUNS_DIR,
    out_dir: Path = ATTACHMENTS_DIR,
    may_record: Path = MAY_RECORD,
) -> list[Path]:
    """Write ``ocean-inference.csv`` and ``.md`` into ``out_dir``; returns the paths."""
    facts, run_names = attachment_facts(snapshot, base, may_record)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "ocean-inference.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["table", "key", "value", "meaning"])
        writer.writerows(facts)
    md_path = out_dir / "ocean-inference.md"
    md_path.write_text(attachment_markdown(facts, run_names, snapshot) + "\n", encoding="utf-8")
    return [csv_path, md_path]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_dirs(spec: str | None) -> list[Path]:
    """Run ids (under snapshots/runs/) or folder paths from a comma list."""
    if not spec:
        return []
    return [Path(r) if "/" in r else UC01_RUNS_DIR / r for r in spec.split(",") if r.strip()]


def cmd_infer(args: argparse.Namespace) -> int:
    """CLI handler for ``infer``: run inference for the composed targets and print the run's card."""
    apply_force_llm(args)
    contacts = [int(c) for c in args.contacts.split(",") if c.strip()] if args.contacts else None
    run_dir = run(
        provider=args.provider,
        model=args.model,
        tier=args.tier,
        pick_name=args.pick,
        sample_name=args.sample,
        previous=args.previous,
        contacts=contacts,
        everyone=args.all,
        limit=args.limit,
        exclude_runs=_run_dirs(args.exclude_runs),
        concurrency=args.concurrency,
        label=args.label,
    )
    print(f"wrote {run_dir}")
    print((run_dir / "RESULTS.md").read_text(encoding="utf-8"))
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    """CLI handler for ``freeze``: rewrite the committed snapshot from the named run folders."""
    path, counts = freeze(_run_dirs(args.runs), output=Path(args.output), replace=args.replace)
    print(
        f"wrote {path} ({counts['profiles']} profiles from {counts['runs']} run(s), "
        f"{counts['dropped']} dropped); rebuild the database with "
        "`python -m substrate.pipeline.build_all --force --from database`"
    )
    return 0


def cmd_attachment(args: argparse.Namespace) -> int:
    """CLI handler for ``attachment``: write the appendix csv/md pair from the snapshot's run folders."""
    for path in attachment_build(out_dir=Path(args.out)):
        print(f"wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the ``infer`` / ``freeze`` / ``attachment`` subcommand parser."""
    parser = argparse.ArgumentParser(
        prog="python -m ucs.uc01_personalization.ocean_inference",
        description=__doc__.split("\n\n")[0],
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("infer", help="Infer profiles for the composed targets into a run folder.")
    add_force_llm_argument(p)
    p.add_argument("--sample", default=None, help="UC-04 sample name (eval/samples/<name>.json)")
    p.add_argument("--pick", default=None, help="UC-01 pick name (its linked contacts)")
    p.add_argument(
        "--previous",
        action="store_true",
        help="everyone with an inferred profile in the snapshot today",
    )
    p.add_argument("--contacts", default=None, help="comma list of contact ids")
    p.add_argument("--all", action="store_true", help="every linked contact")
    p.add_argument("--limit", type=int, default=None, help="first N targets by contact id")
    p.add_argument(
        "--exclude-runs",
        default=None,
        help="comma list of run ids or folders whose profiled reviewers are skipped (continue a batch)",
    )
    p.add_argument("--provider", default="agy", choices=list(PROVIDERS))
    p.add_argument("--model", default=None, help="provider model; the thesis default when omitted")
    p.add_argument("--tier", default=None, help="reasoning tier; the provider default when omitted")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument("--label", default=None, help="run folder tag instead of the generated one")
    p.set_defaults(func=cmd_infer)
    p = sub.add_parser("freeze", help="Rewrite snapshots/ocean_inferred.json from run folders.")
    p.add_argument("--runs", required=True, help="comma list of run ids or folders")
    p.add_argument("--output", default=str(OCEAN_INFERRED_SNAPSHOT))
    p.add_argument(
        "--replace", action="store_true", help="allow dropping reviewers the runs do not cover"
    )
    p.set_defaults(func=cmd_freeze)
    p = sub.add_parser(
        "attachment",
        help="Write attachments/ocean-inference.{csv,md} from the run folders the snapshot names.",
    )
    p.add_argument(
        "--out", default=str(ATTACHMENTS_DIR), help="target folder (default attachments/)"
    )
    p.set_defaults(func=cmd_attachment)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse argv and dispatch to the chosen subcommand's handler."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
