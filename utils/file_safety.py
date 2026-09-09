"""Small helpers that guard generated artifacts: do not clobber, and prove identity.

``require_can_write`` stops a rebuild from silently replacing something;
``file_md5`` is how the chain proves a file on disk is the one that was pinned.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


# ---------------------------------------------------------------------------
# Overwrite guard
# ---------------------------------------------------------------------------


def require_can_write(path: Path | str, *, overwrite: bool, artifact: str = "file") -> Path:
    """
    Return ``path`` if it can be written, otherwise raise ``FileExistsError``.

    Generated thesis artifacts such as SQLite DBs and JSON snapshots are easy
    to replace by mistake.  Writers call this helper before opening a path in
    write mode.  CLIs expose the ``overwrite`` decision as ``--force``.
    """
    resolved = Path(path)
    if resolved.exists() and not overwrite:
        raise FileExistsError(
            f"{artifact} already exists: {resolved}. "
            "Refusing to overwrite it. Re-run with --force, or choose a new output path."
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


# ---------------------------------------------------------------------------
# Content fingerprint
# ---------------------------------------------------------------------------


def file_md5(path: Path | str, *, chunk_size: int = 1 << 20) -> str:
    """Return the MD5 hex digest of a file, read in chunks.

    Used to check a downloaded source against its pinned digest and to fingerprint
    the snapshots a rebuild produced. MD5 is fine here: this detects an incomplete
    download or a changed upstream file, it is not a security boundary.
    """
    digest = hashlib.md5()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()
