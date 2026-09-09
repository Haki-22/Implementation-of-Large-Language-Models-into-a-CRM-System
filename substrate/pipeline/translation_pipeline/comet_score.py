"""Score (English source, Czech translation) pairs with COMET-Kiwi.

Standalone on purpose: only the standard library and the ``unbabel-comet``
package, so this one file runs inside the repository (CPU) and on any GPU
machine given a copy of the pairs file. The result is a quality *report* on
the shipped translation; nothing downstream gates on it.

COMET-Kiwi (``Unbabel/wmt22-cometkiwi-da``, Rei et al., WMT 2022) is a
reference-free quality-estimation model: it reads the source and the machine
translation and predicts the direct-assessment score a human would give, on a
roughly 0-1 scale, without a reference translation. It is the metric the
translator bake-off of May 2026 used to choose Google Cloud Translation v3.
The model is gated on Hugging Face: accept its licence there, then
``huggingface-cli login`` or set ``HUGGING_FACE_HUB_TOKEN``.

Input: JSON lines (plain or ``.gz``) with ``item_id``, ``kind``,
``source_user_id``, ``en``, ``cz`` per line, produced by
``comet_extract_pairs.py`` from the frozen translation. The pair scored is the
translator's actual input and output (``en`` as sent, ``cz_raw`` as returned),
the same pairs the bake-off and the clean-input experiment scored.

Output: CSV ``item_id, kind, source_user_id, comet_score`` plus
``<out>.run-info.json`` (model, package versions, device, throughput).
Resumable: rows already in the CSV are skipped and the file is flushed after
every chunk, so an interrupted run continues where it stopped.

Memory: pairs are bucketed by combined text length and each bucket gets its own
batch size -- short titles and summaries in batches of ``--batch-size``, medium
texts in a quarter of that, long review texts (truncated to 512 tokens by the
model) one at a time. Scores are per item, so batching does not change them;
it only decides whether a 4 GB card fits. The fp32 weights alone take 2.2 GB.

Run (GPU box; --batch-size is the short-text batch, 16 fits a 4 GB card, 64 a 12 GB one):
    python comet_score.py --pairs comet-pairs.jsonl.gz --out stage2-comet.csv --gpus 1 --batch-size 16
Sanity run against the CPU reference of 128 pairs (expect mean |diff| < 0.005):
    python comet_score.py --pairs comet-pairs.jsonl.gz --out smoke.csv --ids-from reference.csv --check reference.csv --gpus 1
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import platform
import statistics
import time
from importlib import metadata
from pathlib import Path

# Reduce allocator fragmentation on small cards; must be set before torch is imported.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

MODEL_ID = "Unbabel/wmt22-cometkiwi-da"
FIELDS = ["item_id", "kind", "source_user_id", "comet_score"]
CHUNK = 2048  # pairs per checkpoint
# Length buckets on len(en) + len(cz) in characters (~4 chars per token):
# upper bound -> divisor of --batch-size. Long texts run one at a time.
BUCKETS = ((300, 1), (1200, 4), (10**9, None))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def load_model(use_gpu: bool):
    """Download (once) and load COMET-Kiwi; ``use_gpu`` is informational, ``predict`` picks the device."""
    from comet import download_model, load_from_checkpoint

    print(f"loading {MODEL_ID} (gpu={use_gpu}) ...", flush=True)
    model = load_from_checkpoint(download_model(MODEL_ID))
    model.eval()
    return model


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def read_pairs(path: Path):
    """Yield one pair dict per line of a JSON-lines file, gzip or plain."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def read_scores(path: Path) -> dict[str, float]:
    """item_id -> comet_score from a CSV that has those two columns."""
    with path.open(encoding="utf-8", newline="") as fh:
        return {row["item_id"]: float(row["comet_score"]) for row in csv.DictReader(fh)}


def _run_info(out_path: Path, *, gpus: int, batch_size: int, scored: int, seconds: float) -> None:
    """Write `<out_path>.run-info.json`: model, package versions, device and throughput for this run."""
    info = {
        "model": MODEL_ID,
        "unbabel_comet": metadata.version("unbabel-comet"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "gpus": gpus,
        "batch_size": batch_size,
        "pairs_scored_this_run": scored,
        "seconds": round(seconds, 1),
        "pairs_per_second": round(scored / seconds, 2) if seconds else None,
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception as exc:  # noqa: BLE001 - informational only
        info["torch"] = f"unavailable: {exc}"
    Path(str(out_path) + ".run-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _bucket(pair: dict) -> int:
    """Return the index into `BUCKETS` for a pair, by combined `en` + `cz` character length."""
    n = len(pair["en"]) + len(pair["cz"])
    for index, (upper, _) in enumerate(BUCKETS):
        if n <= upper:
            return index
    return len(BUCKETS) - 1


def _batch_for(bucket: int, batch_size: int) -> int:
    """Return the batch size for `bucket`: `batch_size` divided by that bucket's divisor in `BUCKETS`."""
    divisor = BUCKETS[bucket][1]
    return 1 if divisor is None else max(1, batch_size // divisor)


def _score_chunk(model, chunk: list[dict], *, batch_size: int, gpus: int) -> list[float]:
    """Score one chunk bucket by bucket; return scores in the chunk's order."""
    scores: dict[int, float] = {}
    for bucket in range(len(BUCKETS)):
        members = [i for i, p in enumerate(chunk) if _bucket(p) == bucket]
        if not members:
            continue
        out = model.predict(
            [{"src": chunk[i]["en"], "mt": chunk[i]["cz"]} for i in members],
            batch_size=_batch_for(bucket, batch_size),
            gpus=gpus,
            progress_bar=False,
        )
        for i, score in zip(members, out.scores, strict=True):
            scores[i] = float(score)
    return [scores[i] for i in range(len(chunk))]


def run(
    pairs_path: Path,
    out_path: Path,
    *,
    gpus: int,
    batch_size: int,
    limit: int | None = None,
    ids_from: Path | None = None,
) -> dict[str, float]:
    """Score every pair not yet in ``out_path``; return all scores (old + new)."""
    done = read_scores(out_path) if out_path.exists() else {}
    wanted = set(read_scores(ids_from)) if ids_from else None
    queue = [
        p
        for p in read_pairs(pairs_path)
        if p["item_id"] not in done and (wanted is None or p["item_id"] in wanted)
    ]
    if limit:
        queue = queue[:limit]
    print(f"{len(queue)} pairs to score ({len(done)} already in {out_path.name})", flush=True)
    if not queue:
        return done
    sizes = [sum(1 for p in queue if _bucket(p) == b) for b in range(len(BUCKETS))]
    print(
        "buckets: "
        + ", ".join(f"{n} pairs @ batch {_batch_for(b, batch_size)}" for b, n in enumerate(sizes)),
        flush=True,
    )

    model = load_model(gpus > 0)
    new_file = not out_path.exists()
    start = time.time()
    scored = 0
    with out_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for i in range(0, len(queue), CHUNK):
            chunk = queue[i : i + CHUNK]
            chunk_scores = _score_chunk(model, chunk, batch_size=batch_size, gpus=gpus)
            for p, score in zip(chunk, chunk_scores, strict=True):
                writer.writerow(
                    {
                        "item_id": p["item_id"],
                        "kind": p["kind"],
                        "source_user_id": p.get("source_user_id") or "",
                        "comet_score": f"{float(score):.4f}",
                    }
                )
                done[p["item_id"]] = float(score)
            fh.flush()
            scored += len(chunk)
            elapsed = time.time() - start
            rate = scored / elapsed if elapsed else 0.0
            eta = (len(queue) - scored) / rate / 60 if rate else 0.0
            print(f"  {scored}/{len(queue)}  {rate:.1f} pairs/s  ETA {eta:.0f} min", flush=True)
    _run_info(
        out_path, gpus=gpus, batch_size=batch_size, scored=scored, seconds=time.time() - start
    )
    return done


def summary(scores: dict[str, float]) -> None:
    """Print the distribution a chapter would quote."""
    vals = sorted(scores.values())
    if not vals:
        return
    q = statistics.quantiles(vals, n=10) if len(vals) >= 10 else [vals[0]] * 9
    print(
        f"n={len(vals)}  mean={statistics.mean(vals):.4f}  median={statistics.median(vals):.4f}  "
        f"p10={q[0]:.4f}  p90={q[8]:.4f}  min={vals[0]:.4f}  max={vals[-1]:.4f}  "
        f"below 0.70: {sum(v < 0.70 for v in vals) / len(vals):.1%}"
    )


def check(scores: dict[str, float], reference: Path) -> None:
    """Compare against a reference CSV on the shared item ids (CPU vs GPU sanity)."""
    ref = read_scores(reference)
    shared = [i for i in ref if i in scores]
    if not shared:
        print("check: no shared item ids with the reference")
        return
    diffs = [abs(scores[i] - ref[i]) for i in shared]
    print(
        f"check vs {reference.name}: n={len(shared)}  mean|diff|={statistics.mean(diffs):.5f}  "
        f"max|diff|={max(diffs):.5f}  >0.01: {sum(d > 0.01 for d in diffs)}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: score the pairs file into a CSV, print the summary, optionally check against a reference."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pairs", type=Path, required=True, help="JSON lines (or .gz) from comet_extract_pairs.py"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="output CSV; appended to when it exists (resume)"
    )
    parser.add_argument("--gpus", type=int, default=0, help="0 = CPU, 1 = one GPU")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="batch for the shortest texts; 16 fits a 4 GB card",
    )
    parser.add_argument("--limit", type=int, default=None, help="score at most N pairs (smoke run)")
    parser.add_argument(
        "--ids-from", type=Path, default=None, help="score only the item ids listed in this CSV"
    )
    parser.add_argument(
        "--check", type=Path, default=None, help="reference CSV to compare against after scoring"
    )
    args = parser.parse_args()

    scores = run(
        args.pairs,
        args.out,
        gpus=args.gpus,
        batch_size=args.batch_size,
        limit=args.limit,
        ids_from=args.ids_from,
    )
    summary(scores)
    if args.check:
        check(scores, args.check)


if __name__ == "__main__":
    main()
