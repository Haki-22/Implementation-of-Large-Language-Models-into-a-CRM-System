"""UC-02 detector eval — N-way A/B on the 69-message PII corpus.

Configurations:
  Fusion (rule + NER):
    1. rule-only           — detect_rule_based (regex + checksums) only
    2. rule + gliner       — fusion: rules win on overlap, gliner adds PERSON/ADDRESS
    3. rule + presidio     — fusion with industry-baseline Presidio analyzer
    4. rule + bardsai      — fusion with bardsai/eu-pii-anonimization-multilang
    5. rule + richielo     — fusion with richielo/small-e-czech (lighter Czech NER)
  NER standalone (no rules — shows pure NER contribution):
    6. gliner only
    7. presidio only
    8. bardsai only
    9. richielo only

NameTag 3 lives in a separate venv (venv-nametag3) with subprocess pipeline.
Driven by ``run_nametag3_on_corpus.py`` (sibling script).

Outputs (sibling of this file):
  summary.json           — overall + per-type metrics for all configs + restored_rate
  per_type.csv           — per-type long-format table
  overall.csv            — 1 row per config: P / R / F1 / restored_rate

Run from the project root:
  $VENV/bin/python -m ucs.uc02_pseudonymization.eval.fusion_refresh.fusion_refresh_harness
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def _find_thesis_root(start: Path) -> Path:
    """Walk up the directory tree until a folder that holds ``ucs/uc02_pseudonymization``,
    directly or under a ``thesis`` subfolder (the layout this harness was written for),
    is found. Works regardless of where this eval dir lives relative to the
    project root. The env var ``THESIS_ROOT`` overrides the search entirely."""
    import os

    env_override = os.environ.get("THESIS_ROOT")
    if env_override:
        candidate = Path(env_override).resolve()
        if (candidate / "ucs" / "uc02_pseudonymization").is_dir():
            return candidate
    here = start.resolve()
    for _ in range(8):
        candidate = here / "thesis"
        if (candidate / "ucs" / "uc02_pseudonymization").is_dir():
            return candidate
        if here.parent == here:
            break
        here = here.parent
    raise RuntimeError(
        f"Could not locate ucs/uc02_pseudonymization from {start}. "
        f"Set the THESIS_ROOT env var to the project root."
    )


THESIS_ROOT = _find_thesis_root(Path(__file__))
sys.path.insert(0, str(THESIS_ROOT))

from ucs.uc02_pseudonymization.code.ner import detect_ner  # noqa: E402
from ucs.uc02_pseudonymization.code.pseudonymizer import (  # noqa: E402
    _fuse_rule_and_ner,
    _load_gold,
    detect_rule_based,
    pseudonymize_text,
    restore_text,
    score_detection,
)

from utils.paths import UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT  # noqa: E402

CORPUS = UC02_PII_CORPUS_SNAPSHOT
GOLD = UC02_PII_GOLD_SNAPSHOT
OUT_DIR = Path(__file__).resolve().parent


# Detector vs gold type-name normalization. Rule detector emits "IBAN", gold
# uses "IBAN_CZ"; without this alias, every IBAN match counts as 1 FP + 1 FN
# and the rule-only F1 drops from 0.88 to 0.72. PSC is detector-only (gold
# treats postal codes as part of ADDRESS, not a standalone type), so PSC spans
# are removed before scoring rather than relabelled.
_TYPE_ALIASES = {"IBAN": "IBAN_CZ"}
_DROP_TYPES = {"PSC"}


def _normalize_types(spans: list[dict]) -> list[dict]:
    """Drop `_DROP_TYPES` spans and rename `_TYPE_ALIASES` types to their gold name."""
    out: list[dict] = []
    for s in spans:
        t = s["pii_type"]
        if t in _DROP_TYPES:
            continue
        if t in _TYPE_ALIASES:
            s = {**s, "pii_type": _TYPE_ALIASES[t]}
        out.append(s)
    return out


_NER_ONLY_BACKENDS = {"gliner", "presidio", "bardsai", "richielo"}
_RULE_FUSION_BACKENDS = {"gliner", "presidio", "bardsai", "richielo"}
# NameTag 3 lives in a separate venv (Keras 3 + UFAL deps conflict with main
# venv). Predictions are pre-computed by ``run_nametag3_on_corpus.py`` and
# loaded from JSONL by message_id below.
NAMETAG3_PREDICTIONS_PATH = Path(__file__).resolve().parent / "nametag3_predictions.jsonl"
_nametag3_cache: dict[str, list[dict]] | None = None


def _load_nametag3_predictions() -> dict[str, list[dict]]:
    """Load and cache the NameTag 3 predictions JSONL, keyed by `message_id`."""
    global _nametag3_cache
    if _nametag3_cache is None:
        if not NAMETAG3_PREDICTIONS_PATH.exists():
            raise FileNotFoundError(
                f"NameTag 3 predictions not found at {NAMETAG3_PREDICTIONS_PATH}. "
                f"Run run_nametag3_on_corpus.py in venv-nametag3 first."
            )
        cache: dict[str, list[dict]] = {}
        with NAMETAG3_PREDICTIONS_PATH.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                cache[row["message_id"]] = row["spans"]
        _nametag3_cache = cache
    return _nametag3_cache


def _detect(text: str, config: str, message_id: str | None = None) -> list[dict]:
    """Return the normalized spans one named configuration detects in `text`.

    `message_id` is required for the ``nametag3`` and ``rule+nametag3``
    configurations, whose predictions are looked up from the pre-computed
    JSONL rather than run inline.
    """
    if config == "rule":
        return _normalize_types(detect_rule_based(text))
    if config.startswith("rule+"):
        backend = config[len("rule+") :]
        if backend == "nametag3":
            if message_id is None:
                raise ValueError("nametag3 fusion needs message_id for lookup")
            ner = _load_nametag3_predictions().get(message_id, [])
            rule = detect_rule_based(text)
            return _normalize_types(_fuse_rule_and_ner(rule, ner))
        if backend not in _RULE_FUSION_BACKENDS:
            raise ValueError(f"unknown fusion backend: {backend}")
        rule = detect_rule_based(text)
        ner = detect_ner(text, backend=backend)
        return _normalize_types(_fuse_rule_and_ner(rule, ner))
    if config == "nametag3":
        if message_id is None:
            raise ValueError("nametag3 standalone needs message_id for lookup")
        return _normalize_types(_load_nametag3_predictions().get(message_id, []))
    if config in _NER_ONLY_BACKENDS:
        return _normalize_types(list(detect_ner(text, backend=config)))
    raise ValueError(f"unknown config: {config}")


def _evaluate(config: str, corpus, gold_by_message) -> dict:
    """Detect, score and check mask/restore round-trip for one configuration over `corpus`."""
    pred_by_message: dict[str, list[dict]] = {}
    restored_ok = 0
    for m in corpus:
        mid, text = m["message_id"], m["text"]
        pred = _detect(text, config, message_id=mid)
        pred_by_message[mid] = pred
        pseud, mapping = pseudonymize_text(text, pred)
        restored_ok += int(restore_text(pseud, mapping) == text)
    summary = score_detection(gold_by_message, pred_by_message)
    summary["detector"] = config
    summary["message_count"] = len(corpus)
    summary["restored_exact_count"] = restored_ok
    summary["restored_exact_rate"] = round(restored_ok / len(corpus), 6)
    return summary


def main() -> None:
    """Run every configuration over the corpus and write summary.json / overall.csv / per_type.csv."""
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    gold_by_message = _load_gold(GOLD)
    allowed = {m["message_id"] for m in corpus}
    gold_by_message = {k: v for k, v in gold_by_message.items() if k in allowed}

    configs = [
        "rule",
        "rule+gliner",
        "rule+presidio",
        "rule+bardsai",
        "rule+richielo",
        "rule+nametag3",
        "gliner",
        "presidio",
        "bardsai",
        "richielo",
        "nametag3",
    ]
    results: dict[str, dict] = {}
    for cfg in configs:
        print(f"[evaluating] {cfg} on {len(corpus)} messages")
        summary = _evaluate(cfg, corpus, gold_by_message)
        o = summary["overall"]
        print(
            f"  P={o['precision']:.3f} R={o['recall']:.3f} F1={o['f1']:.3f} "
            f"(tp={o['tp']} fp={o['fp']} fn={o['fn']}) "
            f"restored={summary['restored_exact_rate']}"
        )
        results[cfg] = summary

    (OUT_DIR / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # overall.csv — 1 row per config
    with (OUT_DIR / "overall.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["config", "precision", "recall", "f1", "tp", "fp", "fn", "restored_rate"])
        for cfg in configs:
            o = results[cfg]["overall"]
            w.writerow(
                [
                    cfg,
                    o["precision"],
                    o["recall"],
                    o["f1"],
                    o["tp"],
                    o["fp"],
                    o["fn"],
                    results[cfg]["restored_exact_rate"],
                ]
            )

    # per_type.csv — long format: config, pii_type, P, R, F1, tp, fp, fn
    all_types: set[str] = set()
    for cfg in configs:
        all_types.update(results[cfg]["by_type"].keys())
    with (OUT_DIR / "per_type.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["config", "pii_type", "precision", "recall", "f1", "tp", "fp", "fn"])
        for cfg in configs:
            by_type = results[cfg]["by_type"]
            for t in sorted(all_types):
                mt = by_type.get(
                    t, {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}
                )
                w.writerow(
                    [cfg, t, mt["precision"], mt["recall"], mt["f1"], mt["tp"], mt["fp"], mt["fn"]]
                )

    print(f"\nWrote summary.json, overall.csv, per_type.csv to {OUT_DIR}")


if __name__ == "__main__":
    main()
