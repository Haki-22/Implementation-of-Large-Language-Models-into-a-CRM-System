"""Select the translation pairs for the dirty-input quality experiment.

Question: the English queue sent to the translator on 2026-05-29 was decoded but
not cleaned, so a small share of the 121 781 items still carried hidden characters (U+FFFD,
private-use glyphs, NBSP, mojibake). We know those items failed more often
(9.3 % against 6.6 %). This selects the ones that *did* translate, plus a matched
control of clean items, so COMET-Kiwi can say whether the ones that got through
also came out worse.

Matching: same ``kind`` (review_summary / review_text / product_title) and the
closest English length among the not-yet-used clean items, ``CONTROLS_PER_ITEM``
controls per dirty item. Deterministic: inputs are sorted and no RNG is used.

Writes ``pairs.csv`` (arm, item_id, kind, en_len, hidden_classes) next to itself.

Run from the project root:
    python substrate/pipeline/translation_pipeline/experiments/clean-input-comet-2026-09-03/build_pairs.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
THESIS = HERE.parents[4]
sys.path.insert(0, str(THESIS))

from utils.paths import STAGE1_TRANSLATE  # noqa: E402
from utils.text_hygiene import CRITICAL_CLASSES, scan_text  # noqa: E402

OUT_CSV = HERE / "pairs.csv"

# Classes that mark an item as "dirty input": every class utils.text_hygiene
# calls critical, plus the invisible whitespace it rewrites. Informational
# classes (DBLSP, WS_EDGE, HTMLENT, foreign scripts) are excluded — they are
# cosmetic and a translator does not trip on them.
HIDDEN_CLASSES = frozenset(CRITICAL_CLASSES | {"NBSP", "LSEP", "SHY"})
CONTROLS_PER_ITEM = 3


# ---------------------------------------------------------------------------
# Dirty-input selection
# ---------------------------------------------------------------------------


def _dirty_item_ids(frozen: dict[str, dict]) -> dict[str, dict[str, int]]:
    """item_id -> hidden-class counts, for every queued item whose English was dirty.

    The frozen translation keeps the English text exactly as it was sent (its
    ``en`` field), so it *is* the sent queue; the separate copy of that queue was
    removed from the repository on 2026-09-03 (md5 in
    ``snapshots/provenance/pre-clean-2026-09-02/_md5sums.txt``).
    """
    dirty: dict[str, dict[str, int]] = {}
    for item_id, row in frozen.items():
        hits = {k: v for k, v in scan_text(row.get("en") or "").items() if k in HIDDEN_CLASSES}
        if hits:
            dirty[item_id] = hits
    return dirty


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Build the dirty-input / matched-clean-control pair list and write it to `pairs.csv`.

    For every queued item whose sent English carried a hidden-character defect
    and that did translate, emits one ``dirty_input`` row plus up to
    ``CONTROLS_PER_ITEM`` ``clean_input`` rows: the nearest-English-length,
    not-yet-used clean items of the same ``kind``.
    """
    frozen = json.loads(STAGE1_TRANSLATE.read_text(encoding="utf-8"))
    dirty = _dirty_item_ids(frozen)

    def translated(item_id: str) -> bool:
        row = frozen.get(item_id)
        return bool(row and row.get("cz_raw"))

    dirty_ok = sorted(item_id for item_id in dirty if translated(item_id))
    print(f"dirty items queued: {len(dirty)}   of those translated: {len(dirty_ok)}")

    # Clean pool, grouped by kind, sorted by English length for nearest-length matching.
    pool: dict[str, list[tuple[int, str]]] = {}
    for item_id, row in frozen.items():
        if item_id in dirty or not row.get("cz_raw"):
            continue
        pool.setdefault(row["kind"], []).append((len(row["en"] or ""), item_id))
    for rows in pool.values():
        rows.sort()

    used: set[str] = set()
    rows_out: list[dict[str, object]] = []

    for item_id in dirty_ok:
        row = frozen[item_id]
        kind = row["kind"]
        en_len = len(row["en"] or "")
        rows_out.append(
            {
                "arm": "dirty_input",
                "item_id": item_id,
                "kind": kind,
                "en_len": en_len,
                "hidden_classes": ";".join(f"{k}={v}" for k, v in sorted(dirty[item_id].items())),
            }
        )
        # Nearest-length unused clean items of the same kind.
        candidates = sorted(
            (abs(length - en_len), cid) for length, cid in pool.get(kind, []) if cid not in used
        )
        for _, cid in candidates[:CONTROLS_PER_ITEM]:
            used.add(cid)
            rows_out.append(
                {
                    "arm": "clean_input",
                    "item_id": cid,
                    "kind": frozen[cid]["kind"],
                    "en_len": len(frozen[cid]["en"] or ""),
                    "hidden_classes": "",
                }
            )

    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["arm", "item_id", "kind", "en_len", "hidden_classes"]
        )
        writer.writeheader()
        writer.writerows(rows_out)

    n_dirty = sum(1 for r in rows_out if r["arm"] == "dirty_input")
    print(f"wrote {OUT_CSV}: {n_dirty} dirty + {len(rows_out) - n_dirty} matched clean controls")


if __name__ == "__main__":
    main()
