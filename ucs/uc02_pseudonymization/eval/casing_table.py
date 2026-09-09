"""The UC-02 detection table under three casings of the corpus of record.

The record corpus is written the way a CRM note is written, with capital letters on
names. Typed input is not always: the demo page found that the record backend misses
"o petru bartošovi" while it reads "o Petru Bartošovi". This runner re-scores the hybrid
configurations (rules + one NER backend) on the corpus as it is, on the corpus in lower
case and in upper case. Gold offsets survive the case change because Czech letters keep
their length; a message whose length would change is dropped and named in ``config.json``.
Two more transforms answer the question whether lemmatisation would help detection:
``lemma`` replaces every word by its ``simplemma`` lemma (Czech names are not in its
dictionary and stay as they are), ``lemma_lower`` lower-cases the result; gold spans are
carried over by word alignment, so the scores are comparable with the other columns.

Everything lands in a run folder like the detection table: ``config.json``,
``summary.json`` (casing → configuration → metrics), ``overall.csv``, ``per_type.csv``,
``predictions/<casing>/<config>.jsonl`` (the spans, re-scorable without the models),
``TABLE.md`` and ``RESULTS.md``. ``--publish`` copies ``TABLE.md`` to
``eval/CASING-COMPARISON.md``, the stable path the README links.

Run from the project root::

    python -m ucs.uc02_pseudonymization.eval.casing_table --publish
    python -m ucs.uc02_pseudonymization.eval.casing_table --configs rules,rules+bardsai,rules+bardsai_v2
    python -m ucs.uc02_pseudonymization.eval.casing_table --casings original,lemma,lower,lemma_lower --tag lemma-...
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from ucs.uc02_pseudonymization.code.ner import (
    DEFAULT_NER_BACKEND,
    LICENCES,
    MODEL_IDS,
    NER_BACKENDS,
    NerBackendError,
)
from ucs.uc02_pseudonymization.code.pseudonymizer import load_gold
from ucs.uc02_pseudonymization.eval import runs
from ucs.uc02_pseudonymization.eval.run_table import evaluate_config
from utils.paths import UC02_DIR, UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT

# The stable copy of the latest published casing table, linked from the README.
CASING_COMPARISON_PATH = UC02_DIR / "eval" / "CASING-COMPARISON.md"

CASINGS: tuple[str, ...] = ("original", "lower", "upper", "lemma", "lemma_lower")
_WORD = re.compile(r"\w+")


# ---------------------------------------------------------------------------
# Recasing the corpus
# ---------------------------------------------------------------------------


def recase(text: str, casing: str) -> str:
    """Return ``text`` in the given casing (``original`` returns it unchanged)."""
    if casing == "original":
        return text
    if casing == "lower":
        return text.lower()
    if casing == "upper":
        return text.upper()
    if casing in ("lemma", "lemma_lower"):
        return lemmatize_text(text, lower=casing == "lemma_lower")[0]
    raise ValueError(f"unknown casing {casing!r}; known: {', '.join(CASINGS)}")


def lemmatize_text(
    text: str, *, lower: bool = False
) -> tuple[str, Callable[[int, int], tuple[int, int]]]:
    """Replace every word by its ``simplemma`` lemma and return a span mapper old → new.

    Digits are kept (identifiers must survive), everything between words is copied as it
    is. Czech names are not in the lemmatiser's dictionary, so "Petru Bartošovi" stays
    "Petru Bartošovi" while "Řekni" becomes "řeknout"; ``lower`` lower-cases the result.
    The mapper turns a gold span of the original into the span of the same words in the
    new text (word starts and ends map exactly; a position inside a word is clamped).
    """
    import simplemma

    starts: list[int] = [0] * (len(text) + 1)
    ends: list[int] = [0] * (len(text) + 1)
    out: list[str] = []
    old_pos = new_pos = 0
    for match in _WORD.finditer(text):
        for k in range(old_pos, match.start()):  # the gap is copied 1:1
            starts[k] = ends[k] = new_pos + (k - old_pos)
        gap = text[old_pos : match.start()]
        out.append(gap)
        new_pos += len(gap)
        word = match.group(0)
        lemma = word if word.isdigit() else str(simplemma.lemmatize(word, lang="cs"))
        if lower:
            lemma = lemma.lower()
        for k in range(match.start(), match.end()):
            offset = min(k - match.start(), len(lemma))
            starts[k] = ends[k] = new_pos + offset
        starts[match.end()] = ends[match.end()] = new_pos + len(lemma)
        out.append(lemma)
        new_pos += len(lemma)
        old_pos = match.end()
    for k in range(old_pos, len(text) + 1):
        starts[k] = ends[k] = new_pos + (k - old_pos)
    out.append(text[old_pos:])
    new_text = "".join(out)

    def map_span(start: int, end: int) -> tuple[int, int]:
        """Return the ``(start, end)`` of the lemmatized text matching a span of the original."""
        return starts[start], ends[end]

    return new_text, map_span


def recase_corpus(
    corpus: list[dict[str, Any]],
    gold: dict[str, list[dict[str, Any]]],
    casing: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[str]]:
    """Transform every message and carry its gold spans over; drop what cannot be mapped.

    ``lower`` / ``upper`` keep every offset (Czech letters keep their length; a message
    whose length would change is dropped and named). ``lemma`` / ``lemma_lower`` change
    lengths, so every gold span is mapped by word alignment and its surface form re-read
    from the new text.
    """
    out_corpus: list[dict[str, Any]] = []
    out_gold: dict[str, list[dict[str, Any]]] = {}
    dropped: list[str] = []
    for message in corpus:
        mid = message["message_id"]
        original = message["text"]
        if casing in ("lemma", "lemma_lower"):
            text, map_span = lemmatize_text(original, lower=casing == "lemma_lower")
            spans = []
            for span in gold.get(mid, []):
                s, e = map_span(int(span["span_start"]), int(span["span_end"]))
                spans.append({**span, "span_start": s, "span_end": e, "surface_form": text[s:e]})
            out_corpus.append({**message, "text": text})
            out_gold[mid] = spans
            continue
        text = recase(original, casing)
        if len(text) != len(original):
            dropped.append(mid)
            continue
        out_corpus.append({**message, "text": text})
        out_gold[mid] = [
            {**span, "surface_form": recase(str(span.get("surface_form", "")), casing)}
            for span in gold.get(mid, [])
        ]
    return out_corpus, out_gold, dropped


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def _write_tables(
    run_dir: Path,
    results: dict[str, dict[str, dict[str, Any]]],
    casings: list[str],
    configs: list[str],
) -> None:
    """Write overall.csv and per_type.csv with a casing column in front."""
    with (run_dir / "overall.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "casing",
                "config",
                "precision",
                "recall",
                "f1",
                "tp",
                "fp",
                "fn",
                "partial_f1",
                "restored_rate",
                "detection_seconds",
            ]
        )
        for casing in casings:
            for cfg in configs:
                s = results[casing].get(cfg)
                if s is None:
                    continue
                o = s["overall"]
                w.writerow(
                    [
                        casing,
                        cfg,
                        o["precision"],
                        o["recall"],
                        o["f1"],
                        o["tp"],
                        o["fp"],
                        o["fn"],
                        s["partial"]["overall"]["f1"],
                        s["unification"]["none"]["restored_exact_rate"],
                        s["detection_seconds"],
                    ]
                )
    all_types = sorted(
        {
            t
            for casing in casings
            for cfg in results[casing]
            for t in results[casing][cfg]["by_type"]
        }
    )
    with (run_dir / "per_type.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["casing", "config", "pii_type", "precision", "recall", "f1", "tp", "fp", "fn"])
        for casing in casings:
            for cfg in configs:
                s = results[casing].get(cfg)
                if s is None:
                    continue
                for t in all_types:
                    m = s["by_type"].get(
                        t, {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}
                    )
                    w.writerow(
                        [
                            casing,
                            cfg,
                            t,
                            m["precision"],
                            m["recall"],
                            m["f1"],
                            m["tp"],
                            m["fp"],
                            m["fn"],
                        ]
                    )


def _f1(summary: dict[str, Any] | None, pii_type: str | None = None) -> str:
    """Strict F1 as text (overall, or of one type), an em dash when absent."""
    if summary is None:
        return "—"
    if pii_type is None:
        return f"{summary['overall']['f1']:.3f}"
    m = summary["by_type"].get(pii_type)
    return f"{m['f1']:.3f}" if m and (m["tp"] + m["fn"]) else "—"


def table_markdown(
    results: dict[str, dict[str, dict[str, Any]]],
    casings: list[str],
    configs: list[str],
    config: dict[str, Any],
) -> str:
    """Render the casing table of one run as Markdown: one row per configuration.

    Columns: strict F1 under each casing, the PERSON and ADDRESS F1 under lower case,
    and the drop from the corpus as written to the corpus in lower case. Sorted by the
    lower-case F1, the rules-alone row on top.
    """
    corpus = config.get("corpus", {})
    ref = "lower" if "lower" in casings else (casings[1] if len(casings) > 1 else casings[0])
    lines = [
        "# UC-02 casing comparison",
        "",
        f"Source run: `eval/runs/{config['run']}/` · corpus: {corpus.get('corpus_id') or corpus.get('corpus_file')} "
        f"({corpus.get('messages')} messages, {corpus.get('gold_spans')} planted items) · "
        f"{config.get('started', '')[:10]}",
        "",
        "Strict F1 (exact span and type) of the rule layer + one NER backend under each transform of "
        "the corpus: as written, lower case, upper case, lemma (every word replaced by its simplemma "
        f"lemma, names untouched), lemma_lower. PERSON and ADDRESS are the strict F1 of that type under "
        f"{ref}. Drop = F1 as written minus F1 under {ref}.",
        "",
        "| configuration | licence | "
        + " | ".join(casings)
        + f" | PERSON {ref} | ADDRESS {ref} | drop |",
        "| --- | --- | " + " | ".join("---" for _ in casings) + " | --- | --- | --- |",
    ]
    rows = [c for c in configs if any(c in results[k] for k in casings)]

    def lower_f1(cfg: str) -> float:
        """Return the strict F1 of `cfg` under `ref` casing, or -1.0 when absent (sorts last)."""
        s = results.get(ref, {}).get(cfg)
        return s["overall"]["f1"] if s else -1.0

    rows.sort(key=lambda c: (c != "rules", -lower_f1(c)))
    for cfg in rows:
        backend = cfg[len("rules+") :] if cfg.startswith("rules+") else None
        licence = LICENCES.get(backend, "?") if backend else "—"
        default = " (default)" if backend == DEFAULT_NER_BACKEND else ""
        per_casing = " | ".join(_f1(results[k].get(cfg)) for k in casings)
        low = results.get(ref, {}).get(cfg)
        orig = results.get("original", {}).get(cfg)
        drop = (
            f"{orig['overall']['f1'] - low['overall']['f1']:+.3f}".replace("+", "−")
            if orig and low
            else "—"
        )
        if drop.startswith("−") and drop[1] == "-":
            drop = "+" + drop[2:]
        lines.append(
            f"| {cfg.replace('+', ' + ')}{default} | {licence} | {per_casing} | "
            f"{_f1(low, 'PERSON')} | {_f1(low, 'ADDRESS')} | {drop} |"
        )
    failed = config.get("failed") or {}
    if failed:
        lines += [
            "",
            "Failed to load: " + "; ".join(f"`{k}` ({v[:80]})" for k, v in failed.items()),
        ]
    lines += [
        "",
        f"`DEFAULT_NER_BACKEND` = `{config.get('default_ner_backend')}`: the record backend of the detection "
        "table. Every number reproduces from the source run folder (`summary.json`, `predictions/`).",
        "",
    ]
    return "\n".join(lines)


def publish_table(run_dir: Path, target: Path = CASING_COMPARISON_PATH) -> Path:
    """Rebuild TABLE.md of a run from its files and copy it to the stable path."""
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    casings = [c for c in config.get("casings", CASINGS) if c in results]
    configs = list(config.get("configs", []))
    text = table_markdown(results, casings, configs, config)
    (run_dir / "TABLE.md").write_text(text, encoding="utf-8")
    target.write_text(text, encoding="utf-8")
    return target


def _card_blocks(
    results: dict[str, dict[str, dict[str, Any]]],
    casings: list[str],
    configs: list[str],
    gold_spans: int,
) -> list[dict[str, Any]]:
    """Build the run-card blocks: one per configuration, one summary line per casing."""
    blocks = []
    for cfg in configs:
        lines = []
        for casing in casings:
            s = results[casing].get(cfg)
            if s is None:
                continue
            o = s["overall"]
            person = s["by_type"].get("PERSON", {})
            lines.append(
                (
                    f"{casing}: strict F1 {o['f1']:.3f}, found {o['tp']} of {gold_spans}, "
                    f"{o['fp']} false alarms",
                    f"names: {person.get('tp', 0)} of {person.get('tp', 0) + person.get('fn', 0)}",
                )
            )
        if lines:
            blocks.append({"name": cfg.replace("+", " + "), "lines": lines})
    return blocks


def write_outputs(
    run_dir: Path,
    *,
    results: dict[str, dict[str, dict[str, Any]]],
    predictions: dict[str, dict[str, dict[str, list[dict[str, Any]]]]],
    casings: list[str],
    configs: list[str],
    identity: dict[str, Any],
    dropped: dict[str, list[str]],
    failed: dict[str, str],
    started: float,
    t0: float,
    limit: int | None,
) -> None:
    """Write config.json, summary.json, the CSVs, the predictions, TABLE.md and the card."""
    backends = [c[len("rules+") :] for c in configs if c.startswith("rules+")]
    config = {
        "run": run_dir.name,
        "kind": "casing-table",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
        "duration_seconds": round(time.monotonic() - t0, 1),
        "corpus": identity,
        "code": runs.code_identity(),
        "models": runs.model_revisions([MODEL_IDS[b] for b in backends if b in MODEL_IDS]),
        "casings": casings,
        "configs": configs,
        "dropped_messages": dropped,
        "failed": failed,
        "default_ner_backend": DEFAULT_NER_BACKEND,
        "limit": limit,
    }
    runs.write_json(run_dir / "config.json", config)
    runs.write_json(run_dir / "summary.json", results)
    _write_tables(run_dir, results, casings, configs)
    (run_dir / "TABLE.md").write_text(
        table_markdown(results, casings, configs, config), encoding="utf-8"
    )
    for casing in casings:
        pred_dir = run_dir / "predictions" / casing
        pred_dir.mkdir(parents=True)
        for cfg, per_message in predictions[casing].items():
            with (pred_dir / f"{cfg}.jsonl").open("w", encoding="utf-8") as f:
                for mid, spans in per_message.items():
                    f.write(
                        json.dumps({"message_id": mid, "spans": spans}, ensure_ascii=False) + "\n"
                    )

    gold_spans = identity.get("gold_spans", 0)
    production = f"rules+{DEFAULT_NER_BACKEND}"
    hybrids = [c for c in configs if c.startswith("rules+") and c in results.get("lower", {})]
    best_lower = max(hybrids, key=lambda c: results["lower"][c]["overall"]["f1"], default=None)
    parts = []
    if production in results.get("original", {}) and production in results.get("lower", {}):
        parts.append(
            f"{production.replace('+', ' + ').capitalize()} scores F1 "
            f"{results['original'][production]['overall']['f1']:.3f} on the corpus as written and "
            f"{results['lower'][production]['overall']['f1']:.3f} in lower case"
        )
    if best_lower and best_lower != production:
        parts.append(
            f"the most case-robust hybrid is {best_lower.replace('+', ' + ')} at "
            f"{results['lower'][best_lower]['overall']['f1']:.3f} in lower case"
        )
    sentence = ("; ".join(parts) + ".") if parts else "No hybrid configuration produced a result."
    runs.write_card(
        run_dir,
        title=(
            f"UC-02 casing — ran on: {identity.get('corpus_id') or identity['corpus_file']} "
            f"({identity['messages']} CRM messages, {gold_spans} planted personal-data items) "
            f"under {', '.join(casings)}"
        ),
        header=[
            ("NER", ", ".join(backends) or "none (rules only)"),
            ("Casings", ", ".join(casings)),
            (
                "Ran",
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(started))}, "
                f"{runs.format_duration(time.monotonic() - t0)}",
            ),
        ],
        blocks=_card_blocks(results, casings, configs, gold_spans),
        sentence=sentence,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="UC-02 detection table under three casings of the corpus of record."
    )
    parser.add_argument("--corpus", type=Path, default=UC02_PII_CORPUS_SNAPSHOT)
    parser.add_argument("--gold", type=Path, default=UC02_PII_GOLD_SNAPSHOT)
    parser.add_argument(
        "--configs",
        default=None,
        help="Comma-separated configurations; default = rules and rules + every NER backend.",
    )
    parser.add_argument(
        "--casings",
        default=",".join(CASINGS),
        help="Comma-separated casings out of original, lower, upper.",
    )
    parser.add_argument("--limit", type=int, default=None, help="First N messages only.")
    parser.add_argument(
        "--tag",
        default=None,
        help="Run folder name after the date; default: casing-table-<corpus>-<n>-configs.",
    )
    parser.add_argument("--runs-dir", type=Path, default=runs.RUNS_DIR)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also copy this run's TABLE.md to eval/CASING-COMPARISON.md (the README's link).",
    )
    parser.add_argument(
        "--publish-from",
        type=Path,
        default=None,
        help="Rebuild TABLE.md of an existing run folder and publish it; no models run.",
    )
    return parser


def main(argv: list[str] | None = None) -> Path:
    """Run the casing table and return the run folder."""
    args = build_parser().parse_args(argv)
    if args.publish_from is not None:
        target = publish_table(args.publish_from)
        print(f"[casing] published {args.publish_from.name} -> {target}")
        return args.publish_from
    t0 = time.monotonic()
    started = time.time()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.limit is not None:
        corpus = corpus[: args.limit]
    gold = load_gold(args.gold)
    allowed = {m["message_id"] for m in corpus}
    gold = {mid: spans for mid, spans in gold.items() if mid in allowed}
    casings = [c.strip() for c in args.casings.split(",") if c.strip()]
    for casing in casings:
        recase("x", casing)  # validates the name
    configs = (
        [c.strip() for c in args.configs.split(",") if c.strip()]
        if args.configs
        else ["rules"] + [f"rules+{b}" for b in NER_BACKENDS]
    )

    results: dict[str, dict[str, dict[str, Any]]] = {c: {} for c in casings}
    predictions: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {c: {} for c in casings}
    dropped: dict[str, list[str]] = {}
    failed: dict[str, str] = {}
    for casing in casings:
        corpus_c, gold_c, dropped_c = recase_corpus(corpus, gold, casing)
        if dropped_c:
            dropped[casing] = dropped_c
        for cfg in configs:
            if cfg in failed:
                continue
            print(f"[casing] {casing}: {cfg} on {len(corpus_c)} messages")
            try:
                summary, preds = evaluate_config(cfg, corpus_c, gold_c, None)
            except NerBackendError as exc:
                failed[cfg] = str(exc)
                print(f"        FAILED: {exc}")
                continue
            results[casing][cfg] = summary
            predictions[casing][cfg] = preds
            o = summary["overall"]
            print(
                f"        P {o['precision']:.3f}  R {o['recall']:.3f}  F1 {o['f1']:.3f}  "
                f"{runs.format_duration(summary['detection_seconds'])}"
            )

    identity = runs.corpus_identity(args.corpus, args.gold)
    identity["messages"] = len(corpus)
    identity["gold_spans"] = sum(len(v) for v in gold.values())
    kept = [c for c in configs if c not in failed]
    tag = args.tag or (
        f"casing-table-{runs.corpus_tag(identity)}-{len(kept)}-configs"
        + (f"-first-{args.limit}-messages" if args.limit else "")
    )
    run_dir = runs.new_run_dir(tag, args.runs_dir)
    write_outputs(
        run_dir,
        results=results,
        predictions=predictions,
        casings=casings,
        configs=kept,
        identity=identity,
        dropped=dropped,
        failed=failed,
        started=started,
        t0=t0,
        limit=args.limit,
    )
    if args.publish:
        publish_table(run_dir)
    print(f"[casing] wrote {run_dir}")
    return run_dir


if __name__ == "__main__":
    main()
