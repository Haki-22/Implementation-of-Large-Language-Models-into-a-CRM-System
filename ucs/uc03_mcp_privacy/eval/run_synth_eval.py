"""Run the UC-03 synthetic-audio eval and report WER + PII recall + categorizer.

Reads the manifest produced by ``generate_synth_audio.py``, transcribes each
WAV via ``stt.transcribe_file`` (the same code path the chat uses), then computes:

- per-clip and aggregate WER via ``jiwer`` (lower-cased, punctuation stripped)
- per-clip and aggregate PII recall — share of ``pii_items`` from the manifest
  whose surface form survives in the hypothesis transcript (case-insensitive
  substring match after digit normalisation)
- categorizer accuracy — both heuristic and (env-permitting) LLM paths
- per-segment, per-voice, per-trick-kind breakdowns matching the synth corpus design

Run from the project root:

    python -m ucs.uc03_mcp_privacy.eval.run_synth_eval

By default uses Whisper ``medium`` (``config.WHISPER_MODEL``).
Override with ``--model tiny|base|small|medium|large-v3-turbo``.

Writes ``synth/results.jsonl`` (per-clip outcomes) and ``synth/summary.json``
(aggregate stats). Stdout shows a compact table.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from statistics import mean, median

import jiwer

# Make absolute UC-package imports work regardless of cwd at run-time.
# Path arithmetic: this file is inside the UC-03 eval directory, so
# parents[3] is the project root.
_THESIS_ROOT = Path(__file__).resolve().parents[3]
if str(_THESIS_ROOT) not in sys.path:
    sys.path.insert(0, str(_THESIS_ROOT))

from ucs.uc03_mcp_privacy.categorizer import categorize_text  # noqa: E402
from ucs.uc03_mcp_privacy.stt import transcribe_file  # noqa: E402

_BASE_DIR = Path(__file__).resolve().parent
_SYNTH_DIR = _BASE_DIR / "synth"
_MANIFEST_PATH = _SYNTH_DIR / "manifest.jsonl"

# TTS engine is currently fixed to edge-tts (Microsoft Edge neural CZ voices)
# — see generate_synth_audio.py. Tag every snapshot with both axes so future
# runs against other STT models or alternative TTS engines never overwrite
# each other. Filenames stay sortable: ``<stem>_<stt>_<tts>.<ext>``.
_TTS_ENGINE_TAG = "edge-tts"

# Normalise text for WER comparison — strip punctuation, lowercase, collapse
# whitespace. Czech accent characters preserved (Whisper produces them too).
_NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


def _norm_for_wer(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    text = text.lower()
    text = _NON_WORD_RE.sub(" ", text)
    return " ".join(text.split())


def _norm_for_pii(text: str) -> str:
    """Looser normalisation for PII recall — also strip diacritics-free spaces
    around digits so 'IČO 12345678' matches '12345678' in the hypothesis."""
    text = text.lower()
    text = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
    text = _NON_WORD_RE.sub(" ", text)
    return " ".join(text.split())


def _pii_recall(pii_items: list[dict], hypothesis: str) -> tuple[int, int]:
    """Return (recovered, total). A PII item counts as recovered iff its
    surface form (after light normalisation) appears in the hypothesis."""
    if not pii_items:
        return 0, 0
    hyp_norm = _norm_for_pii(hypothesis)
    recovered = 0
    for item in pii_items:
        needle = _norm_for_pii(item.get("text", ""))
        if needle and needle in hyp_norm:
            recovered += 1
    return recovered, len(pii_items)


def _load_manifest() -> list[dict]:
    """Read the manifest produced by generate_synth_audio."""
    if not _MANIFEST_PATH.exists():
        raise SystemExit(f"manifest missing: {_MANIFEST_PATH}\nRun generate_synth_audio.py first.")
    rows: list[dict] = []
    for line in _MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _run(model: str) -> None:
    """Transcribe every clip, score it, persist results + summary."""
    manifest = _load_manifest()
    print(f"Loaded {len(manifest)} clips. Model: Whisper {model}.")
    print()

    results: list[dict] = []
    print(
        f"  {'id':<5} {'voice':<22} {'trick':<28} {'WER':>6} {'PII':>6} {'cat':<10} {'latency':>8}"
    )
    print("  " + "-" * 92)

    for row in manifest:
        wav_path = _SYNTH_DIR / row["audio_path"]
        gold = row["gold_transcript"]
        started = time.perf_counter()
        try:
            hyp = transcribe_file(str(wav_path), model_size=model)
        except Exception as exc:  # noqa: BLE001 — log per clip and continue
            print(f"  [{row['id']}] FAILED: {exc}", file=sys.stderr)
            continue
        elapsed = time.perf_counter() - started

        wer = jiwer.wer(_norm_for_wer(gold), _norm_for_wer(hyp))
        pii_rec, pii_total = _pii_recall(row.get("pii_items", []), hyp)
        # Full dispatch: LLM categorizer if available,
        # else heuristic fallback. Production behaviour.
        cat = categorize_text(hyp)
        cat_ok = cat.category == row["expected_category"]

        out = {
            **row,
            "hypothesis": hyp,
            "wer": wer,
            "pii_recall_numerator": pii_rec,
            "pii_recall_denominator": pii_total,
            "category_predicted": cat.category,
            "category_correct": cat_ok,
            "latency_s": round(elapsed, 3),
            "model": model,
        }
        results.append(out)

        pii_str = f"{pii_rec}/{pii_total}" if pii_total else "—"
        cat_str = ("OK " if cat_ok else "MIS") + " " + cat.category[:6]
        trick_label = (row.get("trick_kind") or "")[:26]
        print(
            f"  {row['id']:<5} {row['voice'][6:]:<22} {trick_label:<28} "
            f"{wer * 100:>5.1f}% {pii_str:>6} {cat_str:<10} {elapsed:>7.2f}s"
        )

    stt_tag = f"whisper-{model}"
    results_path = _SYNTH_DIR / f"results_{stt_tag}_{_TTS_ENGINE_TAG}.jsonl"
    summary_path = _SYNTH_DIR / f"summary_{stt_tag}_{_TTS_ENGINE_TAG}.json"

    results_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in results),
        encoding="utf-8",
    )

    summary = _summarise(results, model)
    # Provenance metadata so a future reader can reproduce or cross-reference
    # without grepping the codebase. Every snapshot carries its STT + TTS
    # axes and the clip count it ran over.
    summary["meta"] = {
        "stt_engine": "faster-whisper",
        "stt_model": model,
        "tts_engine": _TTS_ENGINE_TAG,
        "categorizer_mode": "dispatch (LLM if available, else heuristic)",
        "n_clips": len(results),
        "manifest": str(_MANIFEST_PATH.relative_to(_SYNTH_DIR)),
        "results_file": str(results_path.relative_to(_SYNTH_DIR)),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 70)
    print(f"  Whisper {model} on {len(results)} CZ clips (edge-tts synth)")
    print("=" * 70)
    print(f"  WER mean:        {summary['wer_mean'] * 100:6.2f}%")
    print(f"  WER median:      {summary['wer_median'] * 100:6.2f}%")
    print(
        f"  PII recall:      {summary['pii_recall_overall'] * 100:6.2f}% "
        f"({summary['pii_recovered']}/{summary['pii_total']} items)"
    )
    print(
        f"  Categorizer:     {summary['cat_accuracy'] * 100:6.2f}% "
        f"({summary['cat_correct']}/{summary['cat_total']} correct)"
    )
    print(f"  Latency mean:    {summary['latency_mean_s']:6.2f} s")
    print(f"  Latency p50:     {summary['latency_p50_s']:6.2f} s")
    print()
    print("  Per-voice (gender-stratified breakdown):")
    for voice, stats in summary["per_voice"].items():
        print(
            f"    {voice:<25} WER {stats['wer_mean'] * 100:5.2f}% "
            f"PII {stats['pii_recall'] * 100:5.1f}% "
            f"({stats['n']} clips)"
        )
    print()
    print("  Per-segment (clean vs trick segment):")
    for segment, stats in summary["per_segment"].items():
        print(
            f"    {segment:<10} WER {stats['wer_mean'] * 100:5.2f}% "
            f"PII {stats['pii_recall'] * 100:5.1f}% "
            f"cat {stats['cat_accuracy'] * 100:5.1f}% "
            f"({stats['n']} clips)"
        )
    print()
    print(f"  Results: {results_path}")
    print(f"  Summary: {summary_path}")


def _summarise(results: list[dict], model: str) -> dict:
    """Aggregate stats: overall, per-voice, per-segment (clean/trick)."""
    if not results:
        return {"model": model, "n": 0}

    def _stats(rows: list[dict]) -> dict:
        """Aggregate WER, PII recall and categorizer accuracy over one subset of `rows`."""
        wers = [r["wer"] for r in rows]
        pii_num = sum(r["pii_recall_numerator"] for r in rows)
        pii_den = sum(r["pii_recall_denominator"] for r in rows)
        cat_ok = sum(1 for r in rows if r["category_correct"])
        return {
            "n": len(rows),
            "wer_mean": mean(wers) if wers else 0.0,
            "wer_median": median(wers) if wers else 0.0,
            "pii_recall": pii_num / pii_den if pii_den else 0.0,
            "pii_recovered": pii_num,
            "pii_total": pii_den,
            "cat_accuracy": cat_ok / len(rows),
            "cat_correct": cat_ok,
            "cat_total": len(rows),
        }

    overall = _stats(results)
    overall["model"] = model
    overall["latency_mean_s"] = round(mean(r["latency_s"] for r in results), 3)
    overall["latency_p50_s"] = round(median(r["latency_s"] for r in results), 3)
    overall["wer_mean"] = overall["wer_mean"]
    overall["wer_median"] = overall["wer_median"]
    overall["pii_recall_overall"] = overall["pii_recall"]

    voices = sorted({r["voice"] for r in results})
    overall["per_voice"] = {v: _stats([r for r in results if r["voice"] == v]) for v in voices}

    clean = [r for r in results if not r.get("is_trick")]
    trick = [r for r in results if r.get("is_trick")]
    overall["per_segment"] = {"clean": _stats(clean), "trick": _stats(trick)}

    return overall


def main() -> int:
    """CLI entry point: score one Whisper size on the synthetic corpus."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--model",
        default="medium",
        choices=("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"),
        help="Whisper model size. Default 'medium' (config.WHISPER_MODEL).",
    )
    args = p.parse_args()
    _run(args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
