"""Judge a finished run: the cascade as a second pass, one folder per judging.

Reads ``snapshots/runs/<run-id>/messages.jsonl`` (only rows that hold a
generated text), loads each contact from the database (the stored greeting the
judges compare against), runs ``judge.judge_cascade`` under a concurrency limit
and writes ``snapshots/runs/<run-id>/judge-<judge-id>/``:

    config.json       run id, the cascade (level, judges and arbiter with the
                      RESOLVED model ids and tiers, prompt versions), the
                      LLM-switch state, concurrency, counts, timing
    verdicts.jsonl    one trail per message: rules, every judge's booleans,
                      spans and labels, the arbiter, the final state, its reason
    summary.json      per generation level: VALID / PARTIAL / HUMAN by reason,
                      judge agreement, arbitrations, calls; totals per provider
    human-review.md   the sheet for the two human states: every HUMAN row to
                      decide and every PARTIAL row to verify, each with the
                      message, the facts, every verdict and span, and an empty
                      verdict line

The run's own files are never touched; judging the same run again with other
judges is a new folder beside the first.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ucs.uc01_personalization import data
from ucs.uc01_personalization.judge import (
    FINAL_HUMAN,
    FINAL_PARTIAL,
    FINAL_VALID,
    STATUS_FULL,
    Cascade,
    CascadeResult,
    judge_cascade,
)
from utils.llm_switch import llm_calls_source
from utils.paths import UC01_RUNS_DIR

DEFAULT_CONCURRENCY = 4

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def load_run_messages(
    folder: Path,
    *,
    contacts: list[int] | None = None,
    briefs: list[int] | None = None,
) -> list[dict[str, Any]]:
    """The generated rows of a run (skipped and failed rows have no text to judge).

    ``contacts`` / ``briefs`` narrow the pass to a subset, for a smoke run or a
    re-judging of a few rows; the judge folder's config records the filter.
    """
    rows = []
    with (folder / "messages.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if not row.get("text") or row.get("error") or row.get("skipped"):
                continue
            if contacts is not None and row["contact_id"] not in contacts:
                continue
            if briefs is not None and row["brief_id"] not in briefs:
                continue
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


async def _judge_all(
    rows: list[dict[str, Any]],
    contacts: dict[int, data.ContactRecord],
    cascade: Cascade,
    *,
    concurrency: int,
    timeout: int,
) -> list[CascadeResult]:
    """Run ``judge_cascade`` over every row concurrently under a semaphore; results in row order."""
    sem = asyncio.Semaphore(concurrency)

    async def one(row: dict[str, Any]) -> CascadeResult:
        """Judge one row's text against its contact, under the shared semaphore."""
        async with sem:
            return await judge_cascade(
                row["text"], contacts[row["contact_id"]], cascade, timeout=timeout
            )

    return list(await asyncio.gather(*(one(r) for r in rows)))


def _trail(row: dict[str, Any], result: CascadeResult) -> dict[str, Any]:
    """One ``verdicts.jsonl`` line: the message's identifying facts plus the cascade's full trail."""
    return {
        "contact_id": row["contact_id"],
        "brief_id": row["brief_id"],
        "level": row["level"],
        "level_name": row.get("level_name"),
        "gender": row.get("gender"),
        "formal": row.get("formal"),
        "text": row["text"],
        **result.to_dict(),
    }


def judge_run(
    run_id: str,
    cascade: Cascade,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    judge_id: str | None = None,
    runs_dir: Path | None = None,
    timeout: int = 180,
    contacts: list[int] | None = None,
    briefs: list[int] | None = None,
) -> Path:
    """Judge every generated message of a run (or the given subset); return the new judge folder."""
    folder = (runs_dir or UC01_RUNS_DIR) / run_id
    if not folder.exists():
        raise FileNotFoundError(f"no such run: {folder}")
    jid = (
        judge_id or f"judge-{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')}-L{cascade.level}"
    )
    out = folder / jid
    if out.exists():
        raise FileExistsError(f"judge folder exists, a judging is never overwritten: {out}")

    rows = load_run_messages(folder, contacts=contacts, briefs=briefs)
    if not rows:
        raise ValueError(f"nothing to judge in {folder} for contacts={contacts} briefs={briefs}")
    conn = data.connect()
    try:
        records = {cid: data.load_contact(conn, cid) for cid in {r["contact_id"] for r in rows}}
    finally:
        conn.close()

    enabled, source = llm_calls_source()
    started = time.monotonic()
    results = asyncio.run(
        _judge_all(rows, records, cascade, concurrency=concurrency, timeout=timeout)
    )
    trails = [_trail(row, res) for row, res in zip(rows, results, strict=True)]
    summary = summarise(trails)

    out.mkdir(parents=True)
    with (out / "verdicts.jsonl").open("w", encoding="utf-8") as fh:
        for trail in trails:
            fh.write(json.dumps(trail, ensure_ascii=False) + "\n")
    config = {
        "judge_id": jid,
        "run_id": run_id,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cascade": cascade.to_dict(),
        "subset": {"contacts": contacts, "briefs": briefs},
        "llm_calls": {"enabled": enabled, "source": source},
        "concurrency": concurrency,
        "timeout": timeout,
        "messages": len(trails),
        "calls": summary["total"]["calls"],
        "seconds": round(time.monotonic() - started, 1),
    }
    (out / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "human-review.md").write_text(human_sheet(trails, config), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Summary and the human sheet
# ---------------------------------------------------------------------------


def _agreement(trail: dict[str, Any]) -> tuple[int, int, int]:
    """(pairs, pairs both FULL and agreeing, pairs agreeing on the booleans alone)."""
    judges = trail.get("judges") or []
    if len(judges) < 2:
        return 0, 0, 0
    a, b = judges[0], judges[1]
    answered = a["ok"] and b["ok"]
    booleans = int(bool(answered) and a["ok"] == b["ok"])
    full = int(a["status"] == STATUS_FULL and b["status"] == STATUS_FULL and booleans == 1)
    return 1, full, booleans


def summarise(trails: list[dict[str, Any]]) -> dict[str, Any]:
    """Per generation level and in total: the three final states, reasons, agreement, calls."""
    out: dict[str, Any] = {}
    levels = sorted({t["level"] for t in trails}, key=lambda x: (len(x), x))
    for level in [*levels, "total"]:
        mine = trails if level == "total" else [t for t in trails if t["level"] == level]
        pairs = sum(_agreement(t)[0] for t in mine)
        agree = sum(_agreement(t)[1] for t in mine)
        agree_bool = sum(_agreement(t)[2] for t in mine)
        calls_by_provider: Counter = Counter()
        for t in mine:
            for v in t.get("judges") or []:
                calls_by_provider[v["provider"]] += 1
            if t.get("arbiter"):
                calls_by_provider[t["arbiter"]["provider"]] += 1
        out[level] = {
            "name": "" if level == "total" else (mine[0].get("level_name") if mine else ""),
            "n": len(mine),
            FINAL_VALID: sum(t["final"] == FINAL_VALID for t in mine),
            FINAL_PARTIAL: sum(t["final"] == FINAL_PARTIAL for t in mine),
            FINAL_HUMAN: sum(t["final"] == FINAL_HUMAN for t in mine),
            "reasons": dict(Counter(t["reason"] for t in mine)),
            "judge_pairs": pairs,
            # both FULL and the same booleans: what composes a verdict
            "judge_agreement": round(agree / pairs, 3) if pairs else None,
            # the same booleans regardless of span labels: the verdict agreement alone
            "judge_boolean_agreement": round(agree_bool / pairs, 3) if pairs else None,
            "arbitrations": sum(1 for t in mine if t.get("arbiter")),
            "calls": sum(t["calls"] for t in mine),
            "calls_by_provider": dict(calls_by_provider),
        }
    return out


def print_summary(summary: dict[str, Any]) -> None:
    """Print a judge summary as the per-level table the CLI shows after ``judge`` and ``report``."""
    print(
        f"{'level':<6} {'name':<14} {'n':>4} {'VALID':>6} {'PARTIAL':>8} {'HUMAN':>6} {'agree':>6} {'arb':>4} {'calls':>6}  reasons"
    )
    for level, s in summary.items():
        agree = "" if s["judge_agreement"] is None else f"{s['judge_agreement']:.0%}"
        print(
            f"{level:<6} {s['name']:<14} {s['n']:>4} {s[FINAL_VALID]:>6} {s[FINAL_PARTIAL]:>8} "
            f"{s[FINAL_HUMAN]:>6} {agree:>6} {s['arbitrations']:>4} {s['calls']:>6}  {s['reasons']}"
        )


def _verdict_cell(v: dict[str, Any], criterion: str) -> str:
    """One table cell of the human sheet: ok/error mark plus the quoted span and its found/missing/n-a label."""
    if v["status"] == "MALFORMED":
        return "—"
    mark = "ok" if v["ok"][criterion] else "**CHYBA**"
    return f"{mark} „{v['evidence'][criterion]}“ ({v['spans'][criterion]})"


def _row_block(t: dict[str, Any], facts: str) -> str:
    """One message's section of the human sheet: header, facts, quoted text, rules and judge table."""
    lines = [
        f"### contact {t['contact_id']} · brief {t['brief_id']} · level {t['level']} ({t.get('level_name') or ''}) · {t['final']}: `{t['reason']}`",
        "",
        f"Facts: {facts}",
        "",
        *(f"> {ln}" if ln else ">" for ln in t["text"].splitlines()),
        "",
    ]
    rules = t["rules"]
    if rules.get("failures"):
        lines.append(
            f"Rules: **rejected** {', '.join(rules['failures'])}; unchecked {rules.get('unchecked') or '-'}"
        )
    else:
        lines.append(
            f"Rules: accepted; unchecked {rules.get('unchecked') or '-'}; gender sites {rules.get('gender_sites') or '-'}"
        )
    verdicts = [*(t.get("judges") or []), *([t["arbiter"]] if t.get("arbiter") else [])]
    if verdicts:
        lines += [
            "",
            "| role | provider / model / tier | status | verdict | vocative | register | gender |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for v in verdicts:
            lines.append(
                f"| {v['role']} | {v['provider']} / {v['model']} / {v['tier']} | {v['status']} | {v['verdict'] or (v['error'] or '')[:60]} | "
                + " | ".join(_verdict_cell(v, c) for c in ("vocative", "register", "gender"))
                + " |"
            )
        if t.get("arbiter") and t["arbiter"].get("reason"):
            lines.append(f"\nArbiter: {t['arbiter']['reason']}")
    lines += ["", "**Human verdict:** [ ] VALID  [ ] INVALID  — note:", "", "---", ""]
    return "\n".join(lines)


def human_sheet(trails: list[dict[str, Any]], config: dict[str, Any]) -> str:
    """The review sheet: HUMAN rows to decide, then PARTIAL rows to verify."""
    cascade = config["cascade"]
    judges = ", ".join(f"{j['provider']}/{j['model']}/{j['tier']}" for j in cascade["judges"])
    arbiter = cascade["arbiter"]
    head = [
        f"# Human review — run `{config['run_id']}`, judging `{config['judge_id']}` (level {cascade['level']})",
        "",
        f"Judges: {judges}. Arbiter: "
        + (f"{arbiter['provider']}/{arbiter['model']}/{arbiter['tier']}" if arbiter else "none")
        + f". Messages: {config['messages']}, model calls: {config['calls']}.",
        "",
        "HUMAN = the cascade could not accept the message (rules failure, invalid or disagreeing judges): decide. "
        "PARTIAL = every judge in line said ok but one quoted a span that is not in the message: verify. "
        "Spans are labelled found / missing / n/a; a boolean is never changed by the label.",
        "",
    ]
    facts_of: dict[int, str] = {}
    conn = data.connect()
    try:
        for t in trails:
            if t["contact_id"] not in facts_of and t["final"] != FINAL_VALID:
                c = data.load_contact(conn, t["contact_id"])
                facts_of[t["contact_id"]] = (
                    f"greeting {c.name_vocative!r} · gender {c.gender or 'unknown'} · "
                    f"formality {'unknown' if c.formal is None else ('vykání' if c.formal else 'tykání')}"
                )
    finally:
        conn.close()
    sections = []
    for state, title in (
        (FINAL_HUMAN, "To decide (HUMAN)"),
        (FINAL_PARTIAL, "To verify (PARTIAL)"),
    ):
        mine = [t for t in trails if t["final"] == state]
        sections.append(f"## {title}: {len(mine)} message(s)\n")
        sections += [_row_block(t, facts_of[t["contact_id"]]) for t in mine]
    return "\n".join(head + sections)
