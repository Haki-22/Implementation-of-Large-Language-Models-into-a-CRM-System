"""Review-text detection check, treating reviews as negative examples (D-UC02-7).

The planted corpus measures detection against known gold spans. This check runs
over the substrate's review table (``uc_reviews``, Czech translations and English
originals) and counts every returned span as a false alarm. The reviews have no
manual personal-data annotations, so these are detection rates under that
negative-example assumption, not verified false-positive rates.

Rules run over every text; NER configurations run over a seeded sample because a
model call per text is slower. The run folder holds ``config.json``,
``false_alarms.csv`` (hits per type and per 1 000 texts for every configuration),
``examples.md`` (the surface forms behind the numbers) and ``RESULTS.md``.

Run from the project root::

    python -m ucs.uc02_pseudonymization.eval.false_alarms --configs rules,rules+bardsai
    python -m ucs.uc02_pseudonymization.eval.false_alarms --lang cs --sample 2000
"""

from __future__ import annotations

import argparse
import collections
import csv
import random
import sqlite3
import time
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.code.ner import DEFAULT_NER_BACKEND
from ucs.uc02_pseudonymization.eval import runs
from ucs.uc02_pseudonymization.eval.configs import detect_with_config
from utils.paths import SUBSTRATE_DB

_COLUMNS = {"cs": "text_cs", "en": "text_en"}
_EXAMPLES_PER_TYPE = 6


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def load_texts(db_path: Path, lang: str) -> list[str]:
    """Return every non-empty review text in one language from ``uc_reviews``."""
    column = _COLUMNS[lang]
    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            f"select {column} from uc_reviews where {column} is not null and {column} != '' order by id"
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# One configuration
# ---------------------------------------------------------------------------


def evaluate_config(config: str, texts: list[str]) -> dict[str, Any]:
    """Count the false alarms of one configuration over ``texts``."""
    hits: collections.Counter[str] = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    texts_with_hits = 0
    t0 = time.monotonic()
    for text in texts:
        spans = detect_with_config(config, text)
        if spans:
            texts_with_hits += 1
        for span in spans:
            hits[span["pii_type"]] += 1
            bucket = examples[span["pii_type"]]
            if len(bucket) < _EXAMPLES_PER_TYPE and span["surface_form"] not in bucket:
                bucket.append(span["surface_form"])
    seconds = time.monotonic() - t0
    n = len(texts)
    return {
        "config": config,
        "texts": n,
        "seconds": round(seconds, 1),
        "hits": dict(hits),
        "hits_total": sum(hits.values()),
        "per_1000": round(sum(hits.values()) / n * 1000, 2) if n else 0.0,
        "per_1000_by_type": {t: round(c / n * 1000, 2) for t, c in sorted(hits.items())}
        if n
        else {},
        "texts_with_hits": texts_with_hits,
        "texts_with_hits_share": round(texts_with_hits / n, 4) if n else 0.0,
        "examples": dict(examples),
    }


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def write_outputs(
    run_dir: Path, results: list[dict[str, Any]], args: argparse.Namespace, started: float
) -> None:
    """Write config.json, false_alarms.csv, examples.md and RESULTS.md."""
    runs.write_json(
        run_dir / "config.json",
        {
            "run": run_dir.name,
            "kind": "false-alarms",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
            "duration_seconds": round(time.monotonic() - args._t0, 1),
            "source": "uc_reviews (substrate.db), texts without personal data by construction",
            "languages": args.lang,
            "sample_per_ner_config": args.sample,
            "seed": args.seed,
            "configs": args.configs,
            "code": runs.code_identity(),
            "default_ner_backend": DEFAULT_NER_BACKEND,
        },
    )
    runs.write_json(run_dir / "summary.json", results)
    all_types = sorted({t for r in results for t in r["hits"]})
    with (run_dir / "false_alarms.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "config",
                "lang",
                "texts",
                "hits_total",
                "per_1000",
                "texts_with_hits_share",
                "seconds",
                *all_types,
            ]
        )
        for r in results:
            w.writerow(
                [
                    r["config"],
                    r["lang"],
                    r["texts"],
                    r["hits_total"],
                    r["per_1000"],
                    r["texts_with_hits_share"],
                    r["seconds"],
                ]
                + [r["per_1000_by_type"].get(t, 0.0) for t in all_types]
            )
    lines = ["# False-alarm examples", ""]
    for r in results:
        lines.append(f"## {r['config']} ({r['lang']})")
        lines.append("")
        for t, forms in sorted(r["examples"].items()):
            lines.append(f"- {t}: " + " · ".join(f"`{s}`" for s in forms))
        lines.append("")
    (run_dir / "examples.md").write_text("\n".join(lines), encoding="utf-8")

    blocks = []
    for r in results:
        by_type = ", ".join(
            f"{t} {v}" for t, v in sorted(r["per_1000_by_type"].items(), key=lambda kv: -kv[1])
        )
        blocks.append(
            {
                "name": f"{r['config'].replace('+', ' + ')} ({r['lang']})",
                "lines": [
                    (
                        f"{r['per_1000']} false alarms per 1 000 texts",
                        f"{r['hits_total']} in {r['texts']} texts; by type: {by_type}",
                    ),
                    (
                        f"{r['texts_with_hits_share'] * 100:.1f} % of texts got at least one",
                        "a text that would be masked although it holds no personal data",
                    ),
                    (f"run time {runs.format_duration(r['seconds'])}", ""),
                ],
            }
        )
    production = next(
        (r for r in results if r["config"] == f"rules+{DEFAULT_NER_BACKEND}"), results[0]
    )
    sentence = (
        f"On {production['texts']} {production['lang']} texts with no personal data, "
        f"{production['config'].replace('+', ' + ')} raised {production['per_1000']} false alarms per 1 000 texts "
        f"and touched {production['texts_with_hits_share'] * 100:.1f} % of them."
    )
    runs.write_card(
        run_dir,
        title="UC-02 false alarms — ran on: uc_reviews (the substrate's review texts, no personal data)",
        header=[
            (
                "NER",
                ", ".join(sorted({c.split("+")[-1] for c in args.configs if c != "rules"}))
                or "none",
            ),
            ("Configurations", ", ".join(c.replace("+", " + ") for c in args.configs)),
            (
                "Ran",
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(started))}, {runs.format_duration(time.monotonic() - args._t0)}",
            ),
        ],
        blocks=blocks,
        sentence=sentence,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="UC-02 false-alarm check over uc_reviews.")
    parser.add_argument("--db", type=Path, default=SUBSTRATE_DB)
    parser.add_argument("--lang", default="cs,en", help="Comma-separated: cs, en.")
    parser.add_argument("--configs", default=f"rules,rules+{DEFAULT_NER_BACKEND}")
    parser.add_argument(
        "--sample", type=int, default=None, help="Texts per NER configuration (default: all)."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--tag",
        default=None,
        help="Run folder name after the date; default: false-alarms-<configs>-<lang>-reviews-<all|sample>.",
    )
    parser.add_argument("--runs-dir", type=Path, default=runs.RUNS_DIR)
    return parser


def main(argv: list[str] | None = None) -> Path:
    """Run the check and return the run folder."""
    args = build_parser().parse_args(argv)
    args._t0 = time.monotonic()
    started = time.time()
    args.configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    args.lang = [lang.strip() for lang in args.lang.split(",") if lang.strip()]
    results: list[dict[str, Any]] = []
    for lang in args.lang:
        texts = load_texts(args.db, lang)
        for config in args.configs:
            subset = texts
            if config != "rules" and args.sample and args.sample < len(texts):
                subset = random.Random(args.seed).sample(texts, args.sample)
            print(f"[false-alarms] {config} over {len(subset)} {lang} texts")
            result = evaluate_config(config, subset)
            result["lang"] = lang
            results.append(result)
            print(
                f"               {result['per_1000']} per 1 000, {runs.format_duration(result['seconds'])}"
            )
    langs = {"cs": "czech", "en": "english"}
    tag = args.tag or (
        "false-alarms-"
        + "-".join(c.replace("rules+", "") for c in args.configs)
        + "-"
        + "-".join(langs.get(lang, lang) for lang in args.lang)
        + "-reviews-"
        + (f"sample{args.sample}" if args.sample else "all")
    )
    run_dir = runs.new_run_dir(tag, args.runs_dir)
    write_outputs(run_dir, results, args, started)
    print(f"[false-alarms] wrote {run_dir}")
    return run_dir


if __name__ == "__main__":
    main()
