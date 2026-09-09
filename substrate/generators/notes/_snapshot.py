"""Write the committed note snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.file_safety import require_can_write
from utils.paths import NOTES_SNAPSHOT


def save_snapshot(
    notes: list[dict[str, Any]],
    path: Path | str = NOTES_SNAPSHOT,
    *,
    overwrite: bool = False,
) -> None:
    """Write a generated note snapshot."""
    path = require_can_write(path, overwrite=overwrite, artifact="note snapshot")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(notes, fh, indent=2, ensure_ascii=False)
