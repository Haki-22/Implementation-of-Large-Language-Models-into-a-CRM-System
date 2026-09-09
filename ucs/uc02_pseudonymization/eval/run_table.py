"""The UC-02 detection table: every detector configuration on the corpus of record.

For each configuration the runner detects spans in every message, scores them
against the gold (strict and partial), masks and restores the text under each
unification policy, and times the detection. Everything lands in a run folder
(``eval/runs/<date>-<tag>/``): ``config.json``, ``summary.json`` (all metrics),
``overall.csv``, ``per_type.csv``, ``unification.csv``, ``predictions/<config>.jsonl``
(the spans, so the numbers can be re-scored without the models) and ``RESULTS.md``.

Configurations: ``gold`` (the answer key as detector, checks masking and restore),
``rules``, ``rules+<backend>`` and ``<backend>`` for every backend in
``ner.NER_BACKENDS``, plus ``rules+nametag3`` / ``nametag3`` when a predictions file
from ``nametag3_adapter`` is given.

Run from the project root::

    python -m ucs.uc02_pseudonymization.eval.run_table --tag table
    python -m ucs.uc02_pseudonymization.eval.run_table --configs rules,rules+bardsai --tag quick
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.code.ner import (
    DEFAULT_NER_BACKEND,
    LICENCES,
    MODEL_IDS,
    NerBackendError,
)
from ucs.uc02_pseudonymization.code.pseudonymizer import (
    UNIFY_MODES,
    load_gold,
    pseudonymize_text,
    restore_text,
    score_detection,
    unification_summary,
)
from ucs.uc02_pseudonymization.eval import runs
from ucs.uc02_pseudonymization.eval.configs import default_configs, detect_with_config
from ucs.uc02_pseudonymization.eval.nametag3_adapter import load_predictions
from utils.paths import UC02_DIR, UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT

# The stable copy of the latest published table, linked from the README.
NER_COMPARISON_PATH = UC02_DIR / "eval" / "NER-COMPARISON.md"


# ---------------------------------------------------------------------------
# One configuration over the corpus
# ---------------------------------------------------------------------------


def evaluate_config(
    config: str,
    corpus: list[dict[str, Any]],
    gold: dict[str, list[dict[str, Any]]],
    nametag3: dict[str, list[dict[str, Any]]] | None,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Score one configuration; return its summary and its predictions per message."""
    predictions: dict[str, list[dict[str, Any]]] = {}
    t0 = time.monotonic()
    for message in corpus:
        mid = message["message_id"]
        predictions[mid] = detect_with_config(
            config,
            message["text"],
            gold_spans=gold.get(mid, []),
            nametag3_spans=None if nametag3 is None else nametag3.get(mid, []),
        )
    detection_seconds = time.monotonic() - t0

    summary = score_detection(gold, predictions)
    summary["config"] = config
    summary["message_count"] = len(corpus)
    summary["detection_seconds"] = round(detection_seconds, 3)
    summary["unification"] = {}
    for unify in UNIFY_MODES:
        spans = tokens = entities = restored = 0
        for message in corpus:
            masked, mapping = pseudonymize_text(
                message["text"], predictions[message["message_id"]], unify=unify
            )
            restored += int(restore_text(masked, mapping) == message["text"])
            counts = unification_summary(mapping)
            spans += counts["spans"]
            tokens += counts["tokens"]
            entities += counts["entities"]
        summary["unification"][unify] = {
            "spans": spans,
            "tokens": tokens,
            "entities": entities,
            "unification_rate": round(1 - entities / spans, 6) if spans else 0.0,
            "restored_exact_count": restored,
            "restored_exact_rate": round(restored / len(corpus), 6) if corpus else 0.0,
        }
    return summary, predictions


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def _write_tables(run_dir: Path, results: dict[str, dict[str, Any]], configs: list[str]) -> None:
    """Write overall.csv, per_type.csv and unification.csv."""
    with (run_dir / "overall.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "config",
                "precision",
                "recall",
                "f1",
                "tp",
                "fp",
                "fn",
                "partial_precision",
                "partial_recall",
                "partial_f1",
                "restored_rate",
                "detection_seconds",
            ]
        )
        for cfg in configs:
            o = results[cfg]["overall"]
            p = results[cfg]["partial"]["overall"]
            w.writerow(
                [
                    cfg,
                    o["precision"],
                    o["recall"],
                    o["f1"],
                    o["tp"],
                    o["fp"],
                    o["fn"],
                    p["precision"],
                    p["recall"],
                    p["f1"],
                    results[cfg]["unification"]["none"]["restored_exact_rate"],
                    results[cfg]["detection_seconds"],
                ]
            )
    all_types = sorted({t for cfg in configs for t in results[cfg]["by_type"]})
    with (run_dir / "per_type.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["config", "pii_type", "precision", "recall", "f1", "tp", "fp", "fn", "partial_f1"]
        )
        for cfg in configs:
            for t in all_types:
                m = results[cfg]["by_type"].get(
                    t, {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}
                )
                pm = results[cfg]["partial"]["by_type"].get(t, {"f1": 0.0})
                w.writerow(
                    [
                        cfg,
                        t,
                        m["precision"],
                        m["recall"],
                        m["f1"],
                        m["tp"],
                        m["fp"],
                        m["fn"],
                        pm["f1"],
                    ]
                )
    with (run_dir / "unification.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["config", "unify", "spans", "tokens", "entities", "unification_rate", "restored_rate"]
        )
        for cfg in configs:
            for unify, u in results[cfg]["unification"].items():
                w.writerow(
                    [
                        cfg,
                        unify,
                        u["spans"],
                        u["tokens"],
                        u["entities"],
                        u["unification_rate"],
                        u["restored_exact_rate"],
                    ]
                )


def _card_block(
    cfg: str, summary: dict[str, Any], gold_spans: int, n_messages: int
) -> dict[str, Any]:
    """Build one card block for a configuration."""
    o = summary["overall"]
    p = summary["partial"]["overall"]
    restored = summary["unification"]["none"]["restored_exact_count"]
    return {
        "name": cfg.replace("+", " + "),
        "lines": [
            (
                f"found {o['tp']} of {gold_spans} planted items",
                f"share of the personal data that got masked: {o['recall'] * 100:.1f} %",
            ),
            (f"{o['fp']} false alarms", "things masked that were not personal data"),
            (
                f"strict F1 {o['f1']:.3f}, partial {p['f1']:.3f}",
                "combined score; partial credits a half-found address",
            ),
            (f"{restored} of {n_messages} messages restored exactly", "masking is reversible"),
            (f"detection {runs.format_duration(summary['detection_seconds'])}", ""),
        ],
    }


def _f1(summary: dict[str, Any], pii_type: str) -> str:
    """Return the strict F1 of one type as text, or an em dash when the type never occurred."""
    m = summary["by_type"].get(pii_type)
    return f"{m['f1']:.3f}" if m and (m["tp"] + m["fn"]) else "—"


def table_markdown(
    results: dict[str, dict[str, Any]], configs: list[str], config: dict[str, Any]
) -> str:
    """Render the comparison table of one run as Markdown.

    One row per NER backend: licence, strict and partial F1 with the rule layer,
    the four NER types, the standalone F1 (no rules) and the detection time; the
    rules-alone row on top. The header names the run, the corpus and the commit,
    so the file can travel on its own.
    """
    corpus = config.get("corpus", {})
    lines = [
        "# UC-02 NER comparison",
        "",
        f"Source run: `eval/runs/{config['run']}/` · corpus: {corpus.get('corpus_id') or corpus.get('corpus_file')} "
        f"({corpus.get('messages')} messages, {corpus.get('gold_spans')} planted items) · "
        f"{config.get('started', '')[:10]}",
        "",
        "Strict F1 = exact span and type; partial credits a half-found address. The four type columns are "
        "strict F1 with the rule layer. Standalone = the NER alone, no rules. Time = detection over the corpus.",
        "",
        "| NER backend | licence | rules + NER F1 | partial | PERSON | ADDRESS | ORG | DATE | standalone F1 | time |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if "rules" in results:
        r = results["rules"]
        lines.append(
            f"| rules alone | — | {r['overall']['f1']:.3f} | {r['partial']['overall']['f1']:.3f} | "
            f"{_f1(r, 'PERSON')} | {_f1(r, 'ADDRESS')} | {_f1(r, 'ORG')} | {_f1(r, 'DATE')} | — | "
            f"{runs.format_duration(r['detection_seconds'])} |"
        )
    hybrids = [c for c in configs if c.startswith("rules+") and c in results]
    hybrids.sort(key=lambda c: -results[c]["overall"]["f1"])
    for cfg in hybrids:
        backend = cfg[len("rules+") :]
        h = results[cfg]
        alone = results.get(backend)
        default = " (default)" if backend == DEFAULT_NER_BACKEND else ""
        lines.append(
            f"| {backend}{default} | {LICENCES.get(backend, '?')} | {h['overall']['f1']:.3f} | "
            f"{h['partial']['overall']['f1']:.3f} | {_f1(h, 'PERSON')} | {_f1(h, 'ADDRESS')} | "
            f"{_f1(h, 'ORG')} | {_f1(h, 'DATE')} | "
            f"{alone['overall']['f1']:.3f} | "
            if alone
            else f"| {backend}{default} | {LICENCES.get(backend, '?')} | {h['overall']['f1']:.3f} | "
            f"{h['partial']['overall']['f1']:.3f} | {_f1(h, 'PERSON')} | {_f1(h, 'ADDRESS')} | "
            f"{_f1(h, 'ORG')} | {_f1(h, 'DATE')} | — | "
        )
        lines[-1] += f"{runs.format_duration(h['detection_seconds'])} |"
    failed = config.get("failed") or {}
    if failed:
        lines += [
            "",
            "Failed to load: " + "; ".join(f"`{k}` ({v[:80]})" for k, v in failed.items()),
        ]
    lines += [
        "",
        f"`DEFAULT_NER_BACKEND` = `{config.get('default_ner_backend')}`: the best hybrid among licences a CRM "
        "vendor could use. Every number reproduces from the source run folder (`summary.json`, "
        "`predictions/`).",
        "",
    ]
    return "\n".join(lines)


def publish_table(run_dir: Path, target: Path = NER_COMPARISON_PATH) -> Path:
    """Rebuild TABLE.md of a run from its files and copy it to the stable path."""
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    text = table_markdown(results, list(results), config)
    (run_dir / "TABLE.md").write_text(text, encoding="utf-8")
    target.write_text(text, encoding="utf-8")
    return target


def write_outputs(
    run_dir: Path,
    *,
    results: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, list[dict[str, Any]]]],
    configs: list[str],
    identity: dict[str, Any],
    started: float,
    args: argparse.Namespace,
) -> None:
    """Write config.json, summary.json, the CSVs, the predictions and the card."""
    backends = [c[len("rules+") :] for c in configs if c.startswith("rules+")]
    runs.write_json(
        run_dir / "config.json",
        {
            "run": run_dir.name,
            "kind": "detection-table",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
            "duration_seconds": round(time.monotonic() - args._t0, 1),
            "corpus": identity,
            "code": runs.code_identity(),
            "models": runs.model_revisions([MODEL_IDS[b] for b in backends if b in MODEL_IDS]),
            "configs": configs,
            "failed": getattr(args, "_failed", {}),
            "default_ner_backend": DEFAULT_NER_BACKEND,
            "nametag3_predictions": str(args.nametag3_predictions)
            if args.nametag3_predictions
            else None,
            "limit": args.limit,
        },
    )
    runs.write_json(run_dir / "summary.json", results)
    _write_tables(run_dir, results, configs)
    (run_dir / "TABLE.md").write_text(
        table_markdown(
            results,
            configs,
            json.loads((run_dir / "config.json").read_text(encoding="utf-8")),
        ),
        encoding="utf-8",
    )
    pred_dir = run_dir / "predictions"
    pred_dir.mkdir()
    for cfg in configs:
        with (pred_dir / f"{cfg}.jsonl").open("w", encoding="utf-8") as f:
            for mid, spans in predictions[cfg].items():
                f.write(json.dumps({"message_id": mid, "spans": spans}, ensure_ascii=False) + "\n")

    n_messages = identity["messages"]
    gold_spans = identity.get("gold_spans", 0)
    production = f"rules+{DEFAULT_NER_BACKEND}"
    headline = production if production in results else configs[0]
    o = results[headline]["overall"]
    restored = results[headline]["unification"]["none"]["restored_exact_count"]
    sentence = (
        f"{headline.replace('+', ' + ').capitalize()} masked {o['recall'] * 100:.1f} % of the planted "
        f"personal data with {o['fp']} false alarm{'s' if o['fp'] != 1 else ''} (strict F1 {o['f1'] * 100:.1f} %), "
        f"and {restored} of {n_messages} messages restored exactly."
    )
    failed = getattr(args, "_failed", {})
    blocks = [_card_block(cfg, results[cfg], gold_spans, n_messages) for cfg in configs]
    for cfg, error in failed.items():
        blocks.append({"name": cfg.replace("+", " + "), "lines": [(f"failed: {error[:160]}", "")]})
    runs.write_card(
        run_dir,
        title=(
            f"UC-02 detection — ran on: {identity.get('corpus_id') or identity['corpus_file']} "
            f"({n_messages} CRM messages, {gold_spans} planted personal-data items)"
        ),
        header=[
            ("NER", ", ".join(backends) or "none (rules only)"),
            ("Configurations", ", ".join(c.replace("+", " + ") for c in configs)),
            (
                "Ran",
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(started))}, "
                f"{runs.format_duration(time.monotonic() - args._t0)}",
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
    parser = argparse.ArgumentParser(description="UC-02 detection table on the corpus of record.")
    parser.add_argument("--corpus", type=Path, default=UC02_PII_CORPUS_SNAPSHOT)
    parser.add_argument("--gold", type=Path, default=UC02_PII_GOLD_SNAPSHOT)
    parser.add_argument(
        "--configs",
        default=None,
        help="Comma-separated configurations; default = every backend, with and without rules.",
    )
    parser.add_argument(
        "--nametag3-predictions",
        type=Path,
        default=None,
        help="Predictions JSONL from nametag3_adapter; adds the nametag3 configurations.",
    )
    parser.add_argument("--limit", type=int, default=None, help="First N messages only.")
    parser.add_argument(
        "--tag",
        default=None,
        help="Run folder name after the date; default: detection-table-<corpus>-<n>-configs.",
    )
    parser.add_argument("--runs-dir", type=Path, default=runs.RUNS_DIR)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also copy this run's TABLE.md to eval/NER-COMPARISON.md (the README's link).",
    )
    parser.add_argument(
        "--publish-from",
        type=Path,
        default=None,
        help="Rebuild TABLE.md of an existing run folder and publish it; no models run.",
    )
    return parser


def main(argv: list[str] | None = None) -> Path:
    """Run the table and return the run folder."""
    args = build_parser().parse_args(argv)
    if args.publish_from is not None:
        target = publish_table(args.publish_from)
        print(f"[table] published {args.publish_from.name} -> {target}")
        return args.publish_from
    args._t0 = time.monotonic()
    started = time.time()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.limit is not None:
        corpus = corpus[: args.limit]
    gold = load_gold(args.gold)
    allowed = {m["message_id"] for m in corpus}
    gold = {mid: spans for mid, spans in gold.items() if mid in allowed}
    nametag3 = load_predictions(args.nametag3_predictions) if args.nametag3_predictions else None
    configs = (
        [c.strip() for c in args.configs.split(",") if c.strip()]
        if args.configs
        else default_configs(nametag3 is not None)
    )

    results: dict[str, dict[str, Any]] = {}
    predictions: dict[str, dict[str, list[dict[str, Any]]]] = {}
    failed: dict[str, str] = {}
    for cfg in configs:
        print(f"[table] {cfg} on {len(corpus)} messages")
        try:
            summary, preds = evaluate_config(cfg, corpus, gold, nametag3)
        except NerBackendError as exc:
            # A backend that cannot load is a result too: the run keeps the rest.
            failed[cfg] = str(exc)
            print(f"        FAILED: {exc}")
            continue
        results[cfg] = summary
        predictions[cfg] = preds
        o = summary["overall"]
        print(
            f"        P {o['precision']:.3f}  R {o['recall']:.3f}  F1 {o['f1']:.3f}  "
            f"partial F1 {summary['partial']['overall']['f1']:.3f}  "
            f"restored {summary['unification']['none']['restored_exact_rate']:.3f}  "
            f"{runs.format_duration(summary['detection_seconds'])}"
        )

    identity = runs.corpus_identity(args.corpus, args.gold)
    identity["messages"] = len(corpus)
    identity["gold_spans"] = sum(len(v) for v in gold.values())
    tag = args.tag or (
        f"detection-table-{runs.corpus_tag(identity)}-{len(results)}-configs"
        + (f"-first-{args.limit}-messages" if args.limit else "")
    )
    run_dir = runs.new_run_dir(tag, args.runs_dir)
    args._failed = failed
    write_outputs(
        run_dir,
        results=results,
        predictions=predictions,
        configs=[c for c in configs if c in results],
        identity=identity,
        started=started,
        args=args,
    )
    if args.publish:
        publish_table(run_dir)
    print(f"[table] wrote {run_dir}")
    return run_dir


if __name__ == "__main__":
    main()
