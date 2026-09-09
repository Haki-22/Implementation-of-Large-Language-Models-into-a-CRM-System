"""UC-01 command line: status, pick, generate, run, evaluate, faithfulness, report.

Step by step, every step runnable with the model switch off:

    python -m ucs.uc01_personalization status                       # what is in place, no model
    python -m ucs.uc01_personalization pick --force                  # who the runs are for (provenance)
    python -m ucs.uc01_personalization generate --contact 4 --brief 1 --level 1       # no model
    python -m ucs.uc01_personalization generate --contact 4 --brief 1 --level 3a --provider mock
    python -m ucs.uc01_personalization run --levels 0,1              # the no-model rungs on the pick
    python -m ucs.uc01_personalization run --levels all --provider mock          # plumbing, no spend
    python -m ucs.uc01_personalization run --levels 2 --provider codex --force-llm  # a real rung, after a go
    python -m ucs.uc01_personalization evaluate <run-id>             # LSM + overlap, no model
    python -m ucs.uc01_personalization judge <run-id> --level 3 --force-llm  # the judge cascade, 2 calls/message + arbitrations
    python -m ucs.uc01_personalization faithfulness --provider codex --force-llm    # 2 calls per contact
    python -m ucs.uc01_personalization report <run-id>               # the per-level table (+ judge folders)

``generate`` is the unit: one contact, one brief, one level. ``run`` only
loops it over a pick. The frontend calls the same ``generate()``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from ucs.uc01_personalization import data, judge_run, levels, metrics, picker, runner
from ucs.uc01_personalization.generate import generate_sync
from ucs.uc01_personalization.judge import (
    JUDGE_CHOICES,
    Cascade,
    JudgeSpec,
    default_cascade,
    parse_judges,
)
from utils.generation import PROVIDERS, resolve_model, resolve_tier
from utils.hashing import file_sha256
from utils.llm_switch import add_force_llm_argument, apply_force_llm, llm_calls_source
from utils.paths import SUBSTRATE_DB, UC01_PICKS_DIR, UC01_RUNS_DIR


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    """What is in place: the database and its tables, the picks, the runs, the switch."""
    print(
        f"database: {SUBSTRATE_DB} {'present' if SUBSTRATE_DB.exists() else 'MISSING (build_all --from database)'}"
    )
    if SUBSTRATE_DB.exists():
        conn = data.connect()
        try:
            for table in (
                "uc_contacts",
                "uc_message_briefs",
                "uc_reviews",
                "uc_recommendations",
                "uc_topics",
                "uc_aspects",
            ):
                n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                print(f"  {table:<22} {n:>8,d} rows")
            print(f"  core (every level possible): {picker.core_size(conn)} contacts")
        finally:
            conn.close()
    picks = sorted(UC01_PICKS_DIR.glob("*.json")) if UC01_PICKS_DIR.exists() else []
    runs = (
        sorted(p for p in UC01_RUNS_DIR.iterdir() if p.is_dir()) if UC01_RUNS_DIR.exists() else []
    )
    print(f"picks: {[p.stem for p in picks] or 'none (run `pick`)'}")
    print(f"runs:  {len(runs)}" + (f", latest {runs[-1].name}" if runs else ""))
    enabled, source = llm_calls_source()
    print(
        f"model calls: {'ENABLED' if enabled else 'off'} ({source}); levels without a model: 0, 1"
    )
    print(f"levels: {', '.join(levels.LADDER)}")
    return 0


def cmd_pick(args: argparse.Namespace) -> int:
    """Select the reading set and strata by the rule and write the pick file."""
    conn = data.connect()
    try:
        pick = picker.build_pick(conn, name=args.name, per_cell=args.per_cell)
    finally:
        conn.close()
    path = picker.write_pick(pick, overwrite=args.force)
    print(f"core: {pick['core_size']} contacts satisfy the rule")
    for cell, ids in pick["cells"].items():
        print(f"  {cell:<11} {ids}")
    print(f"  strata      {pick['strata']}")
    print(f"  briefs      {pick['briefs']} {pick['brief_titles']}")
    print(f"wrote {path}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """One contact, one brief, one level; prints the message and the verdicts."""
    apply_force_llm(args)
    gen = generate_sync(
        args.contact,
        args.brief,
        args.level,
        provider=args.provider,
        model=args.model,
        tier=args.tier,
        judges=parse_judges(args.judges),
    )
    print(f"contact {gen.contact_id} | brief {gen.brief_id} | level {gen.level} ({gen.level_name})")
    if gen.skipped:
        print(f"skipped: missing {', '.join(gen.skipped)}")
        return 0
    if gen.error:
        print(f"error: {gen.error}")
        return 1
    if args.show_prompt and gen.user_prompt:
        print(
            "--- system prompt ---\n"
            + (gen.system_prompt or "")
            + "\n--- user prompt ---\n"
            + gen.user_prompt
        )
    print("--- message ---")
    print(gen.text)
    print("---")
    if gen.rules is not None:
        print(
            f"rules: {'accepted' if gen.rules['accepted'] else 'rejected ' + ','.join(gen.rules['failures'])}"
        )
    print(f"{'model' if gen.used_model else 'no model'}, {gen.seconds} s")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Loop the pick over briefs and levels; write one run folder."""
    apply_force_llm(args)
    pick = picker.load_pick(args.pick)
    contacts = [int(c) for c in args.contacts.split(",")] if args.contacts else None
    briefs = [int(b) for b in args.briefs.split(",")] if args.briefs else None
    folder = runner.run(
        pick,
        levels_spec=args.levels,
        briefs=briefs,
        contacts=contacts,
        provider=args.provider,
        model=args.model,
        tier=args.tier,
        judges=parse_judges(args.judges),
        concurrency=args.concurrency,
        run_id=args.run_id,
        reuse=[r for r in args.reuse.split(",") if r] if args.reuse else None,
    )
    print(f"run written: {folder}")
    _print_summary(json.loads((folder / "summary.json").read_text(encoding="utf-8")))
    return 0


def _print_summary(summary: dict) -> None:
    """Print a run's per-level table: requested, generated, rules rate, skip reasons and unchecked checks."""
    print(f"{'level':<6} {'name':<16} {'req':>4} {'gen':>4} {'rules':>7}  skipped | unchecked")
    for level, s in summary.items():
        rules = "" if s["rules_rate"] is None else f"{s['rules_rate']:.0%}"
        unchecked = s.get("rules_unchecked") or ""
        print(
            f"{level:<6} {s['name']:<16} {s['requested']:>4} {s['generated']:>4} {rules:>7}  "
            f"{s['skipped'] or ''} | {unchecked}"
        )


def cmd_judge(args: argparse.Namespace) -> int:
    """Run the judge cascade over a finished run; write judge-<id>/ beside it."""
    apply_force_llm(args)
    folder = runner.run_dir(args.run_id)
    if not folder.exists():
        print(f"no such run: {folder}", file=sys.stderr)
        return 1
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    if args.judges or args.arbiter:
        judges = tuple(JudgeSpec.parse(j) for j in (args.judges or "").split(",") if j.strip())
        if not judges:
            judges = default_cascade(args.level, config["provider"]).judges
        arbiter = (
            JudgeSpec.parse(args.arbiter)
            if args.arbiter
            else (default_cascade(3, config["provider"]).arbiter if args.level == 3 else None)
        )
        cascade = Cascade(args.level, judges, arbiter)
    else:
        cascade = default_cascade(args.level, config["provider"])
    out = judge_run.judge_run(
        args.run_id,
        cascade,
        concurrency=args.concurrency,
        judge_id=args.judge_id,
        contacts=[int(c) for c in args.contacts.split(",")] if args.contacts else None,
        briefs=[int(b) for b in args.briefs.split(",")] if args.briefs else None,
    )
    print(f"judge folder written: {out}")
    judge_run.print_summary(json.loads((out / "summary.json").read_text(encoding="utf-8")))
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Style match and vocabulary overlap for a run; no model."""
    folder = runner.run_dir(args.run_id)
    if not folder.exists():
        print(f"no such run: {folder}", file=sys.stderr)
        return 1
    out = metrics.evaluate(folder)
    print(f"wrote {out}")
    summary = json.loads((folder / "metrics-summary.json").read_text(encoding="utf-8"))
    print(f"{'level':<6} {'n':>4} {'LSM':>7} {'overlap':>8} {'chars':>7}")
    for level, s in summary.items():
        print(
            f"{level:<6} {s['n']:>4} {s['lsm_mean'] if s['lsm_mean'] is not None else '':>7} {s['overlap_mean'] if s['overlap_mean'] is not None else '':>8} {s['chars_mean']:>7}"
        )
    return 0


def cmd_faithfulness(args: argparse.Namespace) -> int:
    """Mirror the OCEAN profile and measure how much the psychographic level's text changes."""
    apply_force_llm(args)
    pick = picker.load_pick(args.pick)
    contacts = [int(c) for c in args.contacts.split(",")] if args.contacts else pick["reading_set"]
    brief = args.brief or pick["briefs"][0]
    run_id = args.run_id or runner.make_run_id(pick["name"], args.provider, "faithfulness")
    folder = runner.run_dir(run_id)
    if folder.exists():
        raise FileExistsError(f"run folder exists, a run is never overwritten: {folder}")
    enabled, source = llm_calls_source()
    started = time.monotonic()
    rows = metrics.faithfulness_sync(
        contacts, brief, provider=args.provider, model=args.model, tier=args.tier
    )
    folder.mkdir(parents=True)
    (folder / "faithfulness.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    scored = [r["responsiveness"] for r in rows if "responsiveness" in r]
    # The same provenance as a ladder run: what ran, on which database, with which prompt.
    config = {
        "run_id": run_id,
        "kind": "faithfulness",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pick": pick["name"],
        "brief": brief,
        "level": "5",
        "contacts": contacts,
        "provider": args.provider,
        "model": resolve_model(args.provider, args.model),
        "tier": resolve_tier(args.provider, args.tier, args.model),
        "requested": {"model": args.model, "tier": args.tier},
        "prompt_version": rows[0]["real_generation"]["prompt_version"]
        if rows and "real_generation" in rows[0]
        else None,
        "database": {"path": str(SUBSTRATE_DB), "sha256": file_sha256(SUBSTRATE_DB)},
        "llm_calls": {"enabled": enabled, "source": source},
        "calls": 2 * len(scored),
        "scored": len(scored),
        "skipped": len(rows) - len(scored),
        "mean_responsiveness": round(sum(scored) / len(scored), 4) if scored else None,
        "seconds": round(time.monotonic() - started, 1),
    }
    (folder / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"contacts {len(rows)}, scored {len(scored)}, mean responsiveness {sum(scored) / len(scored):.3f}"
        if scored
        else f"nothing scored: {rows}"
    )
    print(f"wrote {folder / 'faithfulness.json'}")
    return 0


def cmd_card(args: argparse.Namespace) -> int:
    """The one-page card and the appendix files from the runs of record; no model."""
    from pathlib import Path

    from ucs.uc01_personalization import card

    out = card.build(out_path=Path(args.out) if args.out else card.CARD_PATH)
    print(f"wrote {out}")
    print(out.read_text(encoding="utf-8"))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """The per-level table of a run (and its metrics when evaluated)."""
    folder = runner.run_dir(args.run_id)
    if not folder.exists():
        print(f"no such run: {folder}", file=sys.stderr)
        return 1
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    print(
        f"run {config['run_id']}: pick {config['pick']}, provider {config['provider']}/{config['model'] or 'default'}/{config['tier']}, judges {config['judges']}, prompts v{config['prompt_version']}, {config['messages']} messages in {config['seconds']} s"
    )
    _print_summary(json.loads((folder / "summary.json").read_text(encoding="utf-8")))
    if (folder / "metrics-summary.json").exists():
        print("metrics:")
        for level, s in json.loads(
            (folder / "metrics-summary.json").read_text(encoding="utf-8")
        ).items():
            print(
                f"  {level:<6} n={s['n']:<4} LSM={s['lsm_mean']} overlap={s['overlap_mean']} chars={s['chars_mean']}"
            )
    for sub in sorted(folder.glob("judge-*")):
        if (sub / "summary.json").exists():
            print(f"judge folder {sub.name}:")
            judge_run.print_summary(json.loads((sub / "summary.json").read_text(encoding="utf-8")))
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _model_args(p: argparse.ArgumentParser) -> None:
    """Add the shared ``--force-llm``/``--provider``/``--model``/``--tier`` arguments to a subparser."""
    add_force_llm_argument(p)
    p.add_argument("--provider", default="mock", choices=PROVIDERS)
    p.add_argument("--model", default=None)
    p.add_argument("--tier", default="low")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser: one subcommand per step listed in the module docstring."""
    parser = argparse.ArgumentParser(
        prog="python -m ucs.uc01_personalization",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="What is in place; no model.")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "pick", help="Select the reading set + strata by the rule; write the pick file."
    )
    p.add_argument("--name", default=picker.DEFAULT_PICK)
    p.add_argument("--per-cell", type=int, default=picker.PER_CELL)
    p.add_argument("--force", action="store_true", help="Overwrite an existing pick.")
    p.set_defaults(func=cmd_pick)

    p = sub.add_parser("generate", help="One contact, one brief, one level.")
    p.add_argument("--contact", type=int, required=True)
    p.add_argument("--brief", type=int, required=True)
    p.add_argument("--level", default="2", help=f"one of {', '.join(levels.LADDER)}")
    p.add_argument("--judges", default="rules", help=f"comma list of {JUDGE_CHOICES}")
    p.add_argument("--show-prompt", action="store_true")
    _model_args(p)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("run", help="Loop a pick over briefs and levels into a run folder.")
    p.add_argument("--pick", default=picker.DEFAULT_PICK)
    p.add_argument("--levels", default="all", help="comma list of level ids, or 'all'")
    p.add_argument("--briefs", default=None, help="comma list of brief ids (default: the pick's)")
    p.add_argument(
        "--contacts", default=None, help="comma list of contact ids (default: the pick's)"
    )
    p.add_argument("--judges", default="rules", help=f"comma list of {JUDGE_CHOICES}")
    p.add_argument("--concurrency", type=int, default=runner.DEFAULT_CONCURRENCY)
    p.add_argument("--run-id", default=None)
    p.add_argument(
        "--reuse",
        default=None,
        help="comma list of earlier run ids whose identical calls are copied instead of sent",
    )
    _model_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("evaluate", help="LSM + overlap for a run; no model.")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser(
        "faithfulness", help="OCEAN counterfactual on the psychographic level; 2 calls per contact."
    )
    p.add_argument("--pick", default=picker.DEFAULT_PICK)
    p.add_argument("--contacts", default=None)
    p.add_argument("--brief", type=int, default=None)
    p.add_argument("--run-id", default=None)
    _model_args(p)
    p.set_defaults(func=cmd_faithfulness)

    p = sub.add_parser(
        "judge", help="The judge cascade over a finished run; writes judge-<id>/ beside it."
    )
    p.add_argument("run_id")
    p.add_argument("--level", type=int, default=3, choices=(1, 2, 3))
    p.add_argument(
        "--judges",
        default=None,
        help="comma list of provider[:model[:tier]] (default: the providers that did not write the run, claude/agy/codex order)",
    )
    p.add_argument(
        "--arbiter",
        default=None,
        help="provider[:model[:tier]] for level 3 (default: the writer's provider at tier high)",
    )
    p.add_argument("--contacts", default=None, help="comma list of contact ids (default: all rows)")
    p.add_argument("--briefs", default=None, help="comma list of brief ids (default: all rows)")
    p.add_argument("--concurrency", type=int, default=judge_run.DEFAULT_CONCURRENCY)
    p.add_argument("--judge-id", default=None)
    add_force_llm_argument(p)
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("report", help="The per-level table of a run (+ judge folders).")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser(
        "card",
        help="The one-page card eval/RESULTS.md + attachments/uc01-*.{csv,md} from the runs of record; no model calls.",
    )
    p.add_argument("--out", default=None, help="target file (default eval/RESULTS.md)")
    p.set_defaults(func=cmd_card)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse the command line and run the chosen subcommand."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
