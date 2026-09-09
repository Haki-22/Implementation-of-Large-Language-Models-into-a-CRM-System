"""Content hashes for provenance: what file a run folder was produced from.

A run folder names the database it read by sha256, so a number can be traced
to the exact data even after the database is rebuilt. UC-02 (`eval/runs.py`)
and UC-04 (`arena.database_identity`) carry their own copies of this hash from
before this module existed; new code uses this one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    """The hex sha256 of a file, read in chunks (the database is a few hundred MB)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
