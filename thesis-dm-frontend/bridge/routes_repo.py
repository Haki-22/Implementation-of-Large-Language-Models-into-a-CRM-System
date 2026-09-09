"""The repository browser: the tracked tree of the repository as git sees it, one file at a time.

The page reads the READMEs and the code in place, the way a reader browses the public
repository: the tree is ``git ls-files`` (so it shows exactly what is published, never the
runtime folders), a file comes back as text with its kind, a search is ``git grep``. Every
path is checked to stay inside the thesis root. Without git (a tree copy) the tree is a walk
of the folder minus the ignored names.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from utils.paths import THESIS_ROOT

router = APIRouter()

MAX_FILE_BYTES = 400_000
_CACHE_SECONDS = 20
_IGNORED_DIRS = {
    ".git",
    ".runtime",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    "models",
    ".mypy_cache",
}
_BINARY_SUFFIXES = {
    ".gz",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".db",
    ".sqlite",
    ".wav",
    ".mp3",
    ".zip",
    ".pyc",
    ".onnx",
    ".bin",
    ".npy",
    ".npz",
    ".parquet",
}
_LANGUAGES = {
    ".py": "python",
    ".md": "markdown",
    ".json": "json",
    ".jsonl": "json",
    ".toml": "toml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sh": "bash",
    ".jsx": "jsx",
    ".js": "javascript",
    ".css": "css",
    ".html": "html",
    ".csv": "csv",
    ".txt": "text",
    ".sql": "sql",
}

_tracked_cache: tuple[float, list[str], str] = (0.0, [], "")


# ---------------------------------------------------------------------------
# The tracked file list
# ---------------------------------------------------------------------------


def tracked_files() -> list[str]:
    """Relative paths git tracks under the thesis root; a folder walk when git is absent."""
    global _tracked_cache
    stamp, cached, _ = _tracked_cache
    if cached and time.monotonic() - stamp < _CACHE_SECONDS:
        return cached
    files: list[str] = []
    source = "git ls-files"
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=THESIS_ROOT,
            capture_output=True,
            check=True,
            timeout=20,
        ).stdout
        files = [p for p in out.decode("utf-8", errors="replace").split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        files = []
    if not files:
        source = "folder walk"
        for path in sorted(THESIS_ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(THESIS_ROOT)
            if any(part in _IGNORED_DIRS for part in rel.parts):
                continue
            files.append(rel.as_posix())
    _tracked_cache = (time.monotonic(), files, source)
    return files


def tracked_source() -> str:
    """How the tracked list was produced: ``git ls-files`` or ``folder walk``."""
    tracked_files()
    return _tracked_cache[2]


def _clean(path: str) -> str:
    """A repository-relative path without traversal; '' is the root."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail="path_outside_repository")
    return "/".join(parts)


def _kind(rel: str) -> str:
    """Classify ``rel`` by suffix as ``binary``, ``markdown``, ``code`` or ``text``."""
    suffix = Path(rel).suffix.lower()
    if suffix in _BINARY_SUFFIXES:
        return "binary"
    if suffix == ".md":
        return "markdown"
    return "code" if suffix in _LANGUAGES else "text"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/repo/tree")
def repo_tree(path: str = "") -> dict[str, Any]:
    """One folder of the tracked tree: sub-folders, files, and the folder's README if any."""
    rel = _clean(path)
    prefix = rel + "/" if rel else ""
    dirs: dict[str, int] = {}
    files: list[dict[str, Any]] = []
    readmes: set[str] = set()
    for tracked in tracked_files():
        if not tracked.startswith(prefix):
            continue
        rest = tracked[len(prefix) :]
        if "/" in rest:
            head = rest.split("/", 1)[0]
            dirs[head] = dirs.get(head, 0) + 1
            if rest.lower() == f"{head}/readme.md".lower():
                readmes.add(head)
            continue
        full = THESIS_ROOT / tracked
        files.append(
            {
                "name": rest,
                "path": tracked,
                "size": full.stat().st_size if full.exists() else None,
                "kind": _kind(tracked),
            }
        )
    if rel and not dirs and not files:
        raise HTTPException(status_code=404, detail=f"folder_not_found: {rel}")
    readme = next((f["path"] for f in files if f["name"].lower() == "readme.md"), None)
    files.sort(key=lambda f: (f["name"].lower() != "readme.md", f["name"].lower()))
    return {
        "path": rel,
        "crumbs": [
            {"name": p, "path": "/".join(rel.split("/")[: i + 1])}
            for i, p in enumerate(rel.split("/"))
            if rel
        ],
        "dirs": [
            {"name": d, "path": f"{prefix}{d}", "files": n, "readme": d in readmes}
            for d, n in sorted(dirs.items(), key=lambda kv: kv[0].lower())
        ],
        "files": files,
        "readme": readme,
        "total_tracked": len(tracked_files()),
        "source": tracked_source(),
    }


def read_repo_file(rel: str, *, max_bytes: int = MAX_FILE_BYTES) -> dict[str, Any]:
    """One tracked file as text (markdown, code or plain), or a stub for binaries and big files."""
    rel = _clean(rel)
    if rel not in set(tracked_files()):
        raise HTTPException(status_code=404, detail=f"file_not_tracked: {rel}")
    full = (THESIS_ROOT / rel).resolve()
    try:
        full.relative_to(THESIS_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path_outside_repository") from exc
    if not full.is_file():
        raise HTTPException(status_code=404, detail=f"file_not_found: {rel}")
    size = full.stat().st_size
    kind = _kind(rel)
    payload: dict[str, Any] = {
        "path": rel,
        "name": full.name,
        "dir": rel.rsplit("/", 1)[0] if "/" in rel else "",
        "size": size,
        "kind": kind,
        "language": _LANGUAGES.get(full.suffix.lower(), "text"),
        "content": None,
        "truncated": False,
    }
    if kind == "binary":
        return payload
    raw = full.read_bytes()
    if b"\0" in raw[:4096]:
        payload["kind"] = "binary"
        return payload
    if size > max_bytes:
        raw = raw[:max_bytes]
        payload["truncated"] = True
    payload["content"] = raw.decode("utf-8", errors="replace")
    return payload


@router.get("/repo/file")
def repo_file(path: str) -> dict[str, Any]:
    """The text of one tracked file."""
    return read_repo_file(path)


@router.get("/repo/search")
def repo_search(q: str, limit: int = 80) -> dict[str, Any]:
    """``git grep`` over the tracked text files: file, line number, the line."""
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="query too short")
    limit = max(1, min(limit, 300))
    try:
        proc = subprocess.run(
            ["git", "grep", "-I", "-n", "-i", "--no-color", "-e", query, "--"],
            cwd=THESIS_ROOT,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=503, detail=f"git_grep_unavailable: {exc}") from exc
    hits = []
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        hits.append(
            {
                "path": parts[0],
                "line": int(parts[1]) if parts[1].isdigit() else None,
                "text": parts[2][:300],
            }
        )
        if len(hits) >= limit:
            break
    return {"query": query, "hits": hits, "truncated": len(hits) >= limit}
