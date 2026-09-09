"""Command line of UC-04: ``python -m ucs.uc04_matchmaker <status|run|report|facts|attachment|sample|personality|for-uc01|model-run|model-report|card>``.

status                     what is in place (database, customers per branch, raw dump, caches); no computation
run [--arms fast|all|population|a,b] [--langs en,cs] [--regimes crm,population]
    [--protocols full,sampled] [--n-neg 100] [--seed 42] [--label NAME]
                           run the arms into a new folder under eval/runs/; no model calls
report --run DIR           re-render TABLE.md and RESULTS.md of an existing run folder
facts [--population]       the data facts behind the numbers (sparsity, reachability, history
                           length, ties, Czech coverage; with --population the sanity check of
                           ALS on ordinary reviewers) into a run folder; no model calls
attachment [--run DIR] [--facts DIR] [--model-run DIR[,DIR]] [--out DIR]
                           write attachments/uc04-*.{csv,md} and uc04-arms.md from run folders and
                           the registries (a full run and every facts run do this by themselves; this
                           picks the folders by hand)
sample [--name model-arms-100] [--pick uc01-personalization-20-level] [--seed 42] [--force]
                           the fixed customer sample of the model arms and the OCEAN inference
                           (60 A / 20 B / 20 C, UC-01's pick first, then a seeded draw) into
                           eval/samples/<name>.json; no model calls
personality [--arms lightgbm_features,svm_features] [--langs en,cs] [--protocols full,sampled] [--seed 42]
                           the paired personality-feature comparison (none / inferred / sampled profile) into a run
                           folder + attachments/uc04-personality-feature.{csv,md}; no model calls
for-uc01 run [--provider agy] [--model M] [--tier T] [--pick uc01-personalization-20-level] [--limit N] [--top-k 5] --force-llm
                           the outputs for UC-01 (reasons, persona, aspects for the pick's contacts;
                           topics + lifecycle for everyone) into a run folder + attachments/uc04-outputs-for-uc01.{csv,md}
for-uc01 freeze --run DIR [--replace]
                           make a run's handoff.json the file the database build loads (results/uc04_to_uc01_handoff.json)
model-run [--methods all|a,b] [--sample model-arms-100] [--langs en,cs] [--provider agy] [--model M]
    [--tier T] [--limit N] [--reuse DIR] [--concurrency 4] [--n-neg 100] [--seed 42] [--label NAME] --force-llm
                           the model methods (arms/model/) on the fixed sample into a run folder with every call
                           recorded; a run over every method and the whole sample rewrites
                           attachments/uc04-model-methods.{csv,md} and uc04-arms.md; --limit N = a smoke on
                           the first N customers; --provider mock = plumbing without spend
model-report --run DIR     re-render TABLE.md and RESULTS.md of a model-methods run folder
card [--out PATH]          the one-page card eval/RESULTS.md from the runs of record of every kind; no model calls
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from utils.paths import SUBSTRATE_DB

from . import arms as arm_registry
from .arena import PROTOCOLS, REGIMES, RUNS_DIR, report, run
from .attachment import ATTACHMENTS_DIR


def cmd_status(args: argparse.Namespace) -> int:
    """`status`: print what is already in place (database, per-branch counts, raw dump, encoder caches, run folders); no computation."""
    from .data import load_arena
    from .population import raw_reviews_path

    print(f"database: {SUBSTRATE_DB} ({'present' if SUBSTRATE_DB.exists() else 'MISSING'})")
    if SUBSTRATE_DB.exists():
        for lang in ("en", "cs"):
            a = load_arena(lang)
            empty = sum(1 for c in a.customers for it in c.history if not it.text)
            print(
                f"  branch {lang}: {a.n_customers} customers, {a.n_items} products, {sum(len(c.history) for c in a.customers)} history reviews ({empty} with empty text)"
            )
    try:
        print(f"population dump: {raw_reviews_path()} (present)")
    except FileNotFoundError as exc:
        print(f"population dump: MISSING ({exc})")
    from .arms.dense_e5 import CACHE_DIR

    caches = sorted(CACHE_DIR.glob("*.npy")) if CACHE_DIR.exists() else []
    print(f"encoder caches: {len(caches)} in {CACHE_DIR}")
    print(f"arms: {', '.join(arm_registry.ARMS)}")
    print(
        f"run folders: {len([p for p in RUNS_DIR.glob('*') if p.is_dir()]) if RUNS_DIR.exists() else 0} in {RUNS_DIR}"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """`run`: run the requested classical arms into a new run folder and print its results card."""
    run_dir = run(
        arms=args.arms,
        langs=[s for s in args.langs.split(",") if s],
        regimes=[s for s in args.regimes.split(",") if s],
        protocols=[s for s in args.protocols.split(",") if s],
        n_neg=args.n_neg,
        seed=args.seed,
        label=args.label,
    )
    print(f"wrote {run_dir}")
    print((run_dir / "RESULTS.md").read_text(encoding="utf-8"))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """`report`: re-render `TABLE.md` and `RESULTS.md` of an existing arena run folder and print the card."""
    report(Path(args.run))
    print((Path(args.run) / "RESULTS.md").read_text(encoding="utf-8"))
    return 0


def cmd_facts(args: argparse.Namespace) -> int:
    """`facts`: measure the data facts behind the arena's numbers into a new run folder and print the card."""
    from . import facts

    run_dir = facts.run(
        population=args.population, sanity_users=args.sanity_users, seed=args.seed, label=args.label
    )
    print(f"wrote {run_dir}")
    print((run_dir / "RESULTS.md").read_text(encoding="utf-8"))
    return 0


def cmd_attachment(args: argparse.Namespace) -> int:
    """`attachment`: write the appendix files by hand from chosen run folders (default: the newest of each kind)."""
    from . import attachment

    run_dir = Path(args.run) if args.run else attachment.newest_full_run()
    if run_dir is None:
        print("no full arena run (every registered arm) under eval/runs; pass --run <folder>")
        return 1
    facts_dir = Path(args.facts) if args.facts else None
    model_run_dirs = (
        [Path(s) for s in args.model_run.split(",") if s.strip()] if args.model_run else None
    )
    written = attachment.build(
        run_dir=run_dir, facts_dir=facts_dir, model_run_dirs=model_run_dirs, out_dir=Path(args.out)
    )
    for path in written:
        print(f"wrote {path}")
    return 0


def cmd_model_run(args: argparse.Namespace) -> int:
    """`model-run`: run the requested model methods on the fixed sample into a new run folder and print its results card."""
    from utils.llm_switch import apply_force_llm

    from . import model_arena

    apply_force_llm(args)
    run_dir = model_arena.run(
        methods=args.methods,
        role=args.role,
        sample_name=args.sample,
        langs=[s for s in args.langs.split(",") if s],
        provider=args.provider,
        model=args.model,
        tier=args.tier,
        limit=args.limit,
        reuse=Path(args.reuse) if args.reuse else None,
        concurrency=args.concurrency,
        n_neg=args.n_neg,
        seed=args.seed,
        label=args.label,
    )
    print(f"wrote {run_dir}")
    print((run_dir / "RESULTS.md").read_text(encoding="utf-8"))
    if args.provider == "mock":
        print("mock run: plumbing only, delete the folder (mock runs are not provenance)")
    return 0


def cmd_model_report(args: argparse.Namespace) -> int:
    """`model-report`: re-render `TABLE.md` and `RESULTS.md` of an existing model-methods run folder and print the card."""
    from . import model_arena

    model_arena.report(Path(args.run))
    print((Path(args.run) / "RESULTS.md").read_text(encoding="utf-8"))
    return 0


def cmd_card(args: argparse.Namespace) -> int:
    """`card`: rebuild the one-page results card from the runs of record and print it."""
    from . import card

    path = card.build(out_path=Path(args.out) if args.out else card.CARD_PATH)
    print(f"wrote {path}")
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    """`sample`: build and write the fixed customer sample the model arms and the OCEAN inference run on."""
    from ucs.uc01_personalization import picker

    from . import sample as sampling
    from .data import connect

    pick = picker.load_pick(args.pick) if args.pick else None
    conn = connect()
    try:
        built = sampling.build_sample(
            conn, pick=pick, pick_name=args.pick, name=args.name, seed=args.seed
        )
    finally:
        conn.close()
    path = sampling.write_sample(built, overwrite=args.force)
    for group, ids in built["groups"].items():
        print(
            f"group {group}: {len(ids)} customers ({built['pick']['members_per_group'][group]} from the pick)"
        )
    print(f"wrote {path}")
    return 0


def cmd_personality(args: argparse.Namespace) -> int:
    """`personality`: run the paired personality-feature comparison into a new run folder and print its results card."""
    from . import personality

    run_dir = personality.run(
        arms=[s for s in args.arms.split(",") if s],
        langs=[s for s in args.langs.split(",") if s],
        protocols=[s for s in args.protocols.split(",") if s],
        n_neg=args.n_neg,
        seed=args.seed,
        label=args.label,
    )
    print(f"wrote {run_dir}")
    print((run_dir / "RESULTS.md").read_text(encoding="utf-8"))
    return 0


def cmd_for_uc01(args: argparse.Namespace) -> int:
    """`for-uc01 run|freeze`: produce the outputs for UC-01 into a run folder, or freeze one run's handoff as the file the database build loads."""
    from utils.llm_switch import apply_force_llm

    from .outputs_for_uc01 import handoff as handoff_mod
    from .outputs_for_uc01 import run as outputs_run

    if args.action == "run":
        apply_force_llm(args)
        run_dir = outputs_run.run(
            provider=args.provider,
            model=args.model,
            tier=args.tier,
            pick_name=args.pick,
            limit=args.limit,
            top_k=args.top_k,
            concurrency=args.concurrency,
            label=args.label,
        )
        print(f"wrote {run_dir}")
        print((run_dir / "RESULTS.md").read_text(encoding="utf-8"))
        return 0
    path, meta = handoff_mod.freeze(
        Path(args.run) if "/" in args.run else RUNS_DIR / args.run, replace=args.replace
    )
    print(
        f"wrote {path} (run {meta['run']}, prompt {meta['prompt_version']}, {meta['provider']}); rebuild the database with "
        "`python -m substrate.pipeline.build_all --force --from database`"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the `argparse` parser for every subcommand listed in the module docstring."""
    parser = argparse.ArgumentParser(
        prog="python -m ucs.uc04_matchmaker",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("status", help="What is in place; no computation.")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("run", help="Run arms into a new run folder; no model calls.")
    p.add_argument(
        "--arms",
        default="fast",
        help="fast | all | population | comma list (default fast = everything but the encoders)",
    )
    p.add_argument("--langs", default="en,cs")
    p.add_argument("--regimes", default="crm", help=f"comma list of {REGIMES}")
    p.add_argument("--protocols", default=",".join(PROTOCOLS))
    p.add_argument(
        "--n-neg", type=int, default=100, help="negatives per customer in the sampled protocol"
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--label", default=None, help="run folder tag instead of the generated one")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("report", help="Re-render TABLE.md and RESULTS.md of a run folder.")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_report)
    p = sub.add_parser(
        "facts", help="Data facts behind the numbers into a run folder; no model calls."
    )
    p.add_argument(
        "--population",
        action="store_true",
        help="also the population sizes and the ALS sanity check on ordinary reviewers",
    )
    p.add_argument("--sanity-users", type=int, default=2000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--label", default=None)
    p.set_defaults(func=cmd_facts)
    p = sub.add_parser(
        "attachment",
        help="Write attachments/uc04-*.{csv,md} from one run folder (a full run does this by itself).",
    )
    p.add_argument(
        "--run",
        default=None,
        help="arena run folder (default: the newest run that covers every arm)",
    )
    p.add_argument("--facts", default=None, help="facts run folder (default: the newest)")
    p.add_argument(
        "--model-run",
        default=None,
        help="model-methods run folders, comma list, one per method (default: the newest complete folder of every method)",
    )
    p.add_argument(
        "--out", default=str(ATTACHMENTS_DIR), help="target folder (default attachments/)"
    )
    p.set_defaults(func=cmd_attachment)
    p = sub.add_parser(
        "sample",
        help="The fixed customer sample of the model arms into eval/samples/; no model calls.",
    )
    p.add_argument("--name", default="model-arms-100")
    p.add_argument(
        "--pick",
        default="uc01-personalization-20-level",
        help="UC-01 pick whose linked contacts go first",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true", help="overwrite an existing sample file")
    p.set_defaults(func=cmd_sample)
    p = sub.add_parser(
        "personality",
        help="The paired personality-feature comparison of the feature arms; no model calls.",
    )
    p.add_argument("--arms", default="lightgbm_features,svm_features")
    p.add_argument("--langs", default="en,cs")
    p.add_argument("--protocols", default="full,sampled")
    p.add_argument("--n-neg", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--label", default=None)
    p.set_defaults(func=cmd_personality)
    from utils.generation import PROVIDERS
    from utils.llm_switch import add_force_llm_argument

    p = sub.add_parser(
        "model-run",
        help="The model methods on the fixed sample into a run folder (model calls; --provider mock for plumbing).",
    )
    add_force_llm_argument(p)
    p.add_argument("--methods", default="all", help="all | comma list of arms/model/ names")
    p.add_argument("--sample", default="model-arms-100", help="sample under eval/samples/")
    p.add_argument("--langs", default="en,cs")
    p.add_argument("--provider", default="agy", choices=list(PROVIDERS))
    p.add_argument("--model", default=None)
    p.add_argument("--tier", default=None)
    p.add_argument(
        "--limit", type=int, default=None, help="first N customers of every subset (the smoke)"
    )
    p.add_argument(
        "--reuse", default=None, help="an earlier run folder whose identical calls are taken over"
    )
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument(
        "--n-neg", type=int, default=100, help="negatives per customer in the sampled protocol"
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--label", default=None, help="run folder tag instead of the generated one")
    p.add_argument(
        "--role",
        default="record",
        choices=["record", "comparison"],
        help="record (may stand as the run of record of its methods) | comparison (a second "
        "provider on identical inputs, kept beside the record, never replaces it)",
    )
    p.set_defaults(func=cmd_model_run)
    p = sub.add_parser(
        "model-report", help="Re-render TABLE.md and RESULTS.md of a model-methods run folder."
    )
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_model_report)
    p = sub.add_parser(
        "card", help="The one-page card eval/RESULTS.md from the runs of record; no model calls."
    )
    p.add_argument("--out", default=None, help="target file (default eval/RESULTS.md)")
    p.set_defaults(func=cmd_card)
    p = sub.add_parser(
        "for-uc01", help="The outputs for UC-01: run (model calls) or freeze a run's handoff."
    )

    action = p.add_subparsers(dest="action", required=True)
    r = action.add_parser(
        "run", help="Reasons, persona, aspects for the pick; topics + lifecycle for everyone."
    )
    add_force_llm_argument(r)
    r.add_argument("--provider", default="agy", choices=list(PROVIDERS))
    r.add_argument("--model", default=None)
    r.add_argument("--tier", default=None)
    r.add_argument(
        "--pick",
        default="uc01-personalization-20-level",
        help="UC-01 pick whose linked contacts get the prose",
    )
    r.add_argument("--limit", type=int, default=None, help="first N prose contacts (the smoke)")
    r.add_argument("--top-k", type=int, default=5, help="recommendations (and reasons) per contact")
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--label", default=None)
    f = action.add_parser(
        "freeze", help="Copy a run's handoff.json to results/uc04_to_uc01_handoff.json."
    )
    f.add_argument("--run", required=True, help="run id under eval/runs/ or a folder path")
    f.add_argument("--replace", action="store_true", help="overwrite the file of record")
    p.set_defaults(func=cmd_for_uc01)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse `argv` and dispatch to the matching `cmd_*` function."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
