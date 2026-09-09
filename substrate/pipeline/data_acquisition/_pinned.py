"""Verify and fetch the pinned raw sources the substrate is built from.

Both acquisition scripts do the same thing to different data: they know a set of
public files by URL, byte size and MD5, check what is on disk against those pins,
and fetch what is missing. Only the pins and what happens to the bytes afterwards
differ, so the mechanism lives here and each script keeps just its own ``SOURCES``.

Why pin at all: the thesis claims its substrate is derived from specific public
data sets. A pinned digest is what turns that from an assertion into something a
reader can re-check — it proves the file used here is the file the source
publishes, and it fails loudly if an upstream release changes underneath.

A source spec is ``{"url": str, "size": int, "md5": str}`` keyed by file name;
extra keys (such as documentation links) are ignored.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from utils.file_safety import file_md5

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

Sources = dict[str, dict]


def verify(sources: Sources, raw_dir: Path) -> dict[str, str]:
    """Return per-file status: ``ok`` | ``missing`` | ``size-mismatch`` | ``md5-mismatch``.

    Size is checked before the digest so a partial download is reported as what
    it is, without reading gigabytes to say so.
    """
    status: dict[str, str] = {}
    for name, spec in sources.items():
        path = raw_dir / name
        if not path.exists():
            status[name] = "missing"
        elif path.stat().st_size != spec["size"]:
            status[name] = "size-mismatch"
        elif file_md5(path) != spec["md5"]:
            status[name] = "md5-mismatch"
        else:
            status[name] = "ok"
    return status


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download(
    sources: Sources,
    raw_dir: Path,
    *,
    force: bool = False,
    announce: bool = True,
) -> dict[str, str]:
    """Fetch every absent source (or all of them with ``force``); return the verify status.

    Each file lands on a ``.part`` path first and is renamed only once the transfer
    finishes, so an interrupted run leaves no file that would pass an existence
    check but fail its digest.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, spec in sources.items():
        dest = raw_dir / name
        if dest.exists() and not force:
            continue
        if announce:
            print(f"downloading {name} ({spec['size'] / 1e6:.0f} MB) ...", flush=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(spec["url"], tmp)
        tmp.replace(dest)
    return verify(sources, raw_dir)
