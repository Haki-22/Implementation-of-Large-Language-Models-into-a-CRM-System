"""Score the dirty-input vs matched-clean pairs with COMET-Kiwi.

COMET-Kiwi (``Unbabel/wmt22-cometkiwi-da``) is a reference-free quality
estimator: it reads the (English source, Czech output) pair and returns one
score, so no human reference translation is needed. The model runs locally --
no API call, no spend.

Reads ``pairs.csv`` (from ``build_pairs.py``), pulls both texts out of the
frozen stage-1 translation, scores every pair and writes ``scores.csv`` plus a
printed summary.

Run from the project root (CPU; ~2 min for 128 pairs):
    OMP_NUM_THREADS=4 nice -n 19 python \\
      substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/score_pairs.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
THESIS = HERE.parents[4]
sys.path.insert(0, str(THESIS))

from substrate.pipeline.translation_pipeline.comet_score import load_model  # noqa: E402
from utils.paths import STAGE1_TRANSLATE  # noqa: E402

PAIRS_CSV = HERE / "pairs.csv"
SCORES_CSV = HERE / "scores.csv"
BATCH_SIZE = 8


def main() -> None:
    """Score every pair in `pairs.csv` with COMET-Kiwi, write `scores.csv`, and print the per-arm summary.

    Also prints the ``dirty_input`` vs ``clean_input`` mean delta when both
    arms are present, which is the number the experiment is testing for.
    """
    pairs = list(csv.DictReader(PAIRS_CSV.open(encoding="utf-8")))
    frozen = json.loads(STAGE1_TRANSLATE.read_text(encoding="utf-8"))

    data = []
    kept = []
    for row in pairs:
        rec = frozen.get(row["item_id"])
        if not rec or not rec.get("cz_raw"):
            continue
        data.append({"src": rec["en"], "mt": rec["cz_raw"]})
        kept.append(row)

    print(f"scoring {len(data)} pairs with COMET-Kiwi on CPU ...")
    model = load_model(use_gpu=False)
    out = model.predict(data, batch_size=BATCH_SIZE, gpus=0)

    with SCORES_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["arm", "item_id", "kind", "en_len", "hidden_classes", "comet_score"]
        )
        writer.writeheader()
        for row, score in zip(kept, out.scores):
            writer.writerow({**row, "comet_score": round(float(score), 4)})

    by_arm: dict[str, list[float]] = {}
    for row, score in zip(kept, out.scores):
        by_arm.setdefault(row["arm"], []).append(float(score))

    print(f"\nwrote {SCORES_CSV}\n")
    for arm in sorted(by_arm):
        vals = by_arm[arm]
        print(
            f"{arm:12s} n={len(vals):4d}  mean={statistics.mean(vals):.4f}  "
            f"median={statistics.median(vals):.4f}  "
            f"sd={statistics.pstdev(vals):.4f}  min={min(vals):.4f}  max={max(vals):.4f}"
        )
    if {"dirty_input", "clean_input"} <= by_arm.keys():
        delta = statistics.mean(by_arm["dirty_input"]) - statistics.mean(by_arm["clean_input"])
        print(f"\ndelta (dirty - clean) = {delta:+.4f}")


if __name__ == "__main__":
    main()
