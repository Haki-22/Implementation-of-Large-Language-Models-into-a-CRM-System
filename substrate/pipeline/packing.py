"""Compressed transport of the large snapshots: what git ships versus what code reads.

Five snapshot files are too large for a public repository as plain JSON (GitHub
refuses files over 100 MB): the two reviewer files and the catalogue under
``snapshots/amazon/``, the frozen translation under ``provenance/translation/``
and one frozen contacts copy under ``provenance/pre-clean-2026-09-02/``. Git
tracks each as ``<name>.json.gz`` and ignores the plain ``.json``; the code keeps
reading the plain ``.json``, which this module materialises from the ``.gz``
whenever it is missing or older. Nothing else in the repository needs to know
that a compressed form exists.

Compression is gzip level 6 with a zeroed header timestamp, so the same JSON
bytes always give the same ``.gz`` bytes: a regenerated snapshot leaves
``git status`` clean, and ``pack`` / ``unpack`` are byte-exact inverses. After
either direction the two files get the same modification time, which is what
``status`` reads to decide whether anything is stale.

``build_all`` calls ``ensure_unpacked()`` first thing in both modes (a fresh
clone has only the ``.gz``); the producer of the ``amazon/`` files
(``build_clean_snapshots``) calls ``pack`` on what it wrote, so the tracked
form never lags the plain one. The frozen files are never re-packed by any
script: their ``.gz`` is the artifact, unpacked on demand.

Run:
    python -m substrate.pipeline.packing            # status of every packed snapshot
    python -m substrate.pipeline.packing --unpack   # materialise the plain files
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
from pathlib import Path

from utils.paths import (
    CATALOG_EN,
    PRECLEAN_CONTACTS,
    REVIEWERS_CZ_SNAPSHOT,
    REVIEWERS_EN_SNAPSHOT,
    STAGE1_TRANSLATE,
)

# Every snapshot git ships compressed, as the plain path the code reads.
PACKED: tuple[Path, ...] = (
    REVIEWERS_EN_SNAPSHOT,
    REVIEWERS_CZ_SNAPSHOT,
    CATALOG_EN,
    STAGE1_TRANSLATE,
    PRECLEAN_CONTACTS,
)
COMPRESSLEVEL = 6


# ---------------------------------------------------------------------------
# Pack / unpack
# ---------------------------------------------------------------------------


def packed_path(json_path: Path) -> Path:
    """``<name>.json`` -> ``<name>.json.gz`` next to it."""
    return json_path.with_name(json_path.name + ".gz")


def _sync_mtime(source: Path, target: Path) -> None:
    """Copy `source`'s access and modification times onto `target`."""
    stat = source.stat()
    os.utime(target, (stat.st_atime, stat.st_mtime))


def pack(json_path: Path) -> Path:
    """Write the deterministic ``.gz`` of ``json_path`` next to it; return its path."""
    gz_path = packed_path(json_path)
    tmp = gz_path.with_suffix(gz_path.suffix + ".part")
    with json_path.open("rb") as src, tmp.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=COMPRESSLEVEL, mtime=0) as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
    tmp.replace(gz_path)
    _sync_mtime(json_path, gz_path)
    return gz_path


def unpack(json_path: Path) -> Path:
    """Materialise the plain ``json_path`` from its ``.gz``; return ``json_path``."""
    gz_path = packed_path(json_path)
    tmp = json_path.with_suffix(json_path.suffix + ".part")
    with gzip.open(gz_path, "rb") as src, tmp.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1 << 20)
    tmp.replace(json_path)
    _sync_mtime(gz_path, json_path)
    return json_path


# ---------------------------------------------------------------------------
# Status and ensure
# ---------------------------------------------------------------------------


def status(paths: tuple[Path, ...] = PACKED) -> dict[str, str]:
    """Per plain path: ``ok`` | ``needs-unpack`` | ``needs-pack`` | ``missing`` (neither form)."""
    out: dict[str, str] = {}
    for json_path in paths:
        gz_path = packed_path(json_path)
        has_json, has_gz = json_path.exists(), gz_path.exists()
        if not has_json and not has_gz:
            out[str(json_path)] = "missing"
        elif not has_json or (has_gz and gz_path.stat().st_mtime > json_path.stat().st_mtime):
            out[str(json_path)] = "needs-unpack"
        elif not has_gz or json_path.stat().st_mtime > gz_path.stat().st_mtime:
            out[str(json_path)] = "needs-pack"
        else:
            out[str(json_path)] = "ok"
    return out


def ensure_unpacked(paths: tuple[Path, ...] = PACKED, *, announce: bool = True) -> list[Path]:
    """Materialise every plain file that is missing or older than its ``.gz``."""
    done = []
    for json_path, state in zip(paths, status(paths).values(), strict=True):
        if state == "needs-unpack":
            if announce:
                print(f"unpacking {packed_path(json_path).name} ...", flush=True)
            done.append(unpack(json_path))
    return done


def ensure_packed(paths: tuple[Path, ...] = PACKED, *, announce: bool = True) -> list[Path]:
    """Write every ``.gz`` that is missing or older than its plain file."""
    done = []
    for json_path, state in zip(paths, status(paths).values(), strict=True):
        if state == "needs-pack":
            if announce:
                print(f"packing {json_path.name} ...", flush=True)
            done.append(pack(json_path))
    return done


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: print the status, or ``--unpack`` the plain files."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--unpack",
        action="store_true",
        help="materialise every plain .json that is missing or stale",
    )
    args = parser.parse_args()
    if args.unpack:
        for path in ensure_unpacked():
            print(f"  unpacked {path}")
    for path, state in status().items():
        print(f"  {state:13s} {path}")


if __name__ == "__main__":
    main()
