"""Extract the translated pairs of the frozen translation into one portable file.

Reads ``snapshots/provenance/translation/stage1-translate.json`` (read-only) and
writes ``snapshots/intermediate/comet-pairs.jsonl.gz``: one line per item with a
non-empty ``cz_raw`` and no error -- ``item_id``, ``kind``, ``source_user_id``,
``en`` (as sent to the translator), ``cz`` (as returned). That file is the only
input ``comet_score.py`` needs, so the scoring can run on a machine without this
repository (a GPU box).

Run:
    python -m substrate.pipeline.translation_pipeline.comet_extract_pairs
"""

from __future__ import annotations

import gzip
import json

from utils.file_safety import file_md5
from utils.paths import SNAPSHOTS_DIR, STAGE1_TRANSLATE

OUT = SNAPSHOTS_DIR / "intermediate" / "comet-pairs.jsonl.gz"


def main() -> None:
    """Write the pairs file and print its row count and md5."""
    data = json.loads(STAGE1_TRANSLATE.read_text(encoding="utf-8"))
    n = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for item_id, rec in data.items():  # dict order = frozen file order
            if not rec.get("cz_raw") or rec.get("error"):
                continue
            fh.write(
                json.dumps(
                    {
                        "item_id": item_id,
                        "kind": rec["kind"],
                        "source_user_id": rec.get("source_user_id"),
                        "en": rec["en"],
                        "cz": rec["cz_raw"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n += 1
    print(f"wrote {OUT} : {n} pairs, {OUT.stat().st_size / 1e6:.1f} MB, md5 {file_md5(OUT)}")


if __name__ == "__main__":
    main()
