"""UC-03 evaluation metrics.

Public API:

- ``wer(reference, hypothesis)`` → Word Error Rate (jiwer-backed, fallback
  to pure Python edit distance if jiwer unavailable).
- ``cer(reference, hypothesis)`` → Character Error Rate.
- ``pii_recall(gold_spans, predicted_spans)`` → fraction of gold PII
  spans the pseudonymizer detected (partial-overlap match by default).
- ``leak_rate(transport_payloads, gold_surface_forms)`` → fraction of
  payloads (e.g. categorizer prompts, MCP request args) that still
  contain raw PII surface forms after the envelope.
- ``latency_stats(durations_ms)`` → p50 / p95 / mean over a list of
  per-sample latencies.

All functions are pure (no I/O, no env reads) so the runner can call them
under any harness; ``run_synth_eval.py`` is the thin orchestration glue.
"""

from __future__ import annotations

import statistics
from typing import Any, Iterable


# ---------------------------------------------------------------- WER / CER


def _normalize(text: str) -> str:
    """Return `text` lower-cased with whitespace collapsed, for WER/CER comparison."""
    return " ".join((text or "").strip().split()).lower()


def wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate. Returns 0.0 on empty reference."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0
    try:
        import jiwer

        return float(jiwer.wer(ref, hyp))
    except Exception:
        return _edit_distance_rate(ref.split(), hyp.split())


def cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate. Returns 0.0 on empty reference."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0
    try:
        import jiwer

        return float(jiwer.cer(ref, hyp))
    except Exception:
        return _edit_distance_rate(list(ref), list(hyp))


def _edit_distance_rate(ref: list[str], hyp: list[str]) -> float:
    """Return the Levenshtein edit distance between `ref` and `hyp`, divided by ``len(ref)``."""
    if not ref:
        return 0.0
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m] / max(n, 1)


# ---------------------------------------------------------------- PII recall


def _spans_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return whether spans `a` and `b` (each with `start` / `end`) overlap at all."""
    return not (a["end"] <= b["start"] or b["end"] <= a["start"])


def pii_recall(
    gold_spans: list[dict[str, Any]],
    predicted_spans: list[dict[str, Any]],
    *,
    require_type_match: bool = False,
) -> dict[str, float | int]:
    """Per-entity recall: fraction of gold spans detected by the pseudonymizer.

    ``gold_spans`` and ``predicted_spans`` are lists of dicts with at least
    ``start``, ``end``, and ``pii_type`` keys. A predicted span counts as a
    hit if it overlaps a gold span; ``require_type_match=True`` adds the
    pii_type equality constraint (PERSON ≠ EMAIL even if positions match).
    """
    if not gold_spans:
        return {"hits": 0, "total": 0, "recall": 0.0}

    hits = 0
    for gold in gold_spans:
        for pred in predicted_spans:
            if not _spans_overlap(gold, pred):
                continue
            if require_type_match and gold.get("pii_type") != pred.get("pii_type"):
                continue
            hits += 1
            break

    return {"hits": hits, "total": len(gold_spans), "recall": round(hits / len(gold_spans), 4)}


# ---------------------------------------------------------------- leak rate


def leak_rate(
    transport_payloads: Iterable[str],
    gold_surface_forms: Iterable[str],
) -> dict[str, float | int]:
    """Fraction of transport payloads that still contain raw PII.

    A payload is a string that was actually sent over the wire (LLM prompt
    body, MCP arguments JSON, audit args_hash input, etc.). The metric is
    falsifiable: 0.0 = no raw PII observed; >0 = envelope failure or
    misconfiguration.
    """
    forms = [f for f in (s.strip() for s in gold_surface_forms) if f]
    payloads = list(transport_payloads)
    if not payloads or not forms:
        return {"leaks": 0, "total": len(payloads), "leak_rate": 0.0}

    leaks = 0
    for payload in payloads:
        if any(form in payload for form in forms):
            leaks += 1

    return {
        "leaks": leaks,
        "total": len(payloads),
        "leak_rate": round(leaks / len(payloads), 4),
    }


# ---------------------------------------------------------------- latency


def latency_stats(durations_ms: Iterable[float]) -> dict[str, float | int]:
    """p50, p95, mean over a list of per-sample latencies (milliseconds)."""
    values = [float(v) for v in durations_ms if v is not None]
    if not values:
        return {"n": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0}
    values_sorted = sorted(values)
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "p50": round(_percentile(values_sorted, 50), 2),
        "p95": round(_percentile(values_sorted, 95), 2),
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return the `pct`-th percentile (0-100) of already-sorted `sorted_values`, linearly interpolated."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return d0 + d1
