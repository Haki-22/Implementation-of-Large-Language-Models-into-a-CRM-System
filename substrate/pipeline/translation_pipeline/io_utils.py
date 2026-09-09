"""Shared IO + path helpers for stage 1 (``stage1_translate.py``).

``comet_score.py`` deliberately imports nothing from here so it stays portable.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from utils.paths import REVIEWERS_CZ_SNAPSHOT, SNAPSHOTS_DIR, STAGE1_TRANSLATE

INTERMEDIATE_DIR = SNAPSHOTS_DIR / "intermediate"

ENGLISH_USERS_PATH = INTERMEDIATE_DIR / "english-amazon.json"
ENGLISH_ITEMS_PATH = INTERMEDIATE_DIR / "english-items.jsonl"
# The frozen result of the one-time run (read only, lives under snapshots/provenance/).
STAGE1_PATH = STAGE1_TRANSLATE
# Where a re-run under --unfreeze writes; the frozen file is never touched.
STAGE1_OUT_PATH = INTERMEDIATE_DIR / "stage1-translate.json"
CZECH_USERS_PATH = REVIEWERS_CZ_SNAPSHOT


# ---------------------------------------------------------------------------
# JSONL
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> Iterator[dict]:
    """Yield one dict per non-empty line of a JSON-lines file."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


# ---------------------------------------------------------------------------
# Stage 1 artifact
# ---------------------------------------------------------------------------


def load_stage1() -> dict[str, dict]:
    """Return {item_id: {item_id, kind, source_user_id, asin, en, cz_raw, attempts, error}}."""
    if not STAGE1_PATH.exists():
        return {}
    return json.loads(STAGE1_PATH.read_text(encoding="utf-8"))


def save_stage1(records: dict[str, dict]) -> None:
    """Write a stage-1 result to ``intermediate/stage1-translate.json``.

    Never to the frozen file: ``snapshots/provenance/`` is evidence and is not
    regenerated or edited. A re-run under ``--unfreeze`` therefore produces a new
    artifact next to the queue, and pointing the chain at it is a deliberate,
    separate step.
    """
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    STAGE1_OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
