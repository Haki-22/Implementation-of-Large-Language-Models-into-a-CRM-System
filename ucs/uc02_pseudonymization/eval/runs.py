"""Run folders and results cards for UC-02 evaluations (D-UC02-5).

Every evaluation writes into its own folder under ``eval/runs/<date>-<tag>/``:
``config.json`` (what ran on what: corpus identity and hashes, code commit,
package versions, model revisions, the arguments), the machine-readable results
(JSON, CSV, per-message predictions) and ``RESULTS.md``, a one-page card a reader
can attach as it is. A run folder is the provenance of a number and is never
edited; a rerun makes a new folder.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Any

from utils.paths import THESIS_ROOT, UC02_DIR  # noqa: F401

RUNS_DIR = UC02_DIR / "eval" / "runs"

# Packages whose versions decide what a detector does.
_TRACKED_PACKAGES = (
    "transformers",
    "torch",
    "optimum",
    "onnxruntime",
    "gliner",
    "presidio_analyzer",
    "spacy",
)


# ---------------------------------------------------------------------------
# Identity: corpus, code, models
# ---------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    """Return ``path`` relative to the project root (``THESIS_ROOT``) when it lies inside, else as given."""
    try:
        return str(path.resolve().relative_to(THESIS_ROOT.resolve()))
    except ValueError:
        return str(path)


def corpus_identity(corpus_path: Path, gold_path: Path | None = None) -> dict[str, Any]:
    """Describe the corpus a run scored: name, size, hashes, manifest id if any."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    identity: dict[str, Any] = {
        "corpus_file": _display_path(corpus_path),
        "corpus_sha256": file_sha256(corpus_path),
        "messages": len(corpus),
    }
    # The record pair has corpus-manifest.json, the backup pair corpus-manifest-mock.json.
    suffix = "-mock" if "-mock" in corpus_path.name else ""
    manifest = corpus_path.with_name(f"corpus-manifest{suffix}.json")
    if manifest.exists():
        identity["corpus_id"] = json.loads(manifest.read_text(encoding="utf-8")).get("corpus_id")
    if gold_path is not None and gold_path.exists():
        gold_lines = [
            line for line in gold_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        identity["gold_file"] = _display_path(gold_path)
        identity["gold_sha256"] = file_sha256(gold_path)
        identity["gold_spans"] = len(gold_lines)
    return identity


def code_identity(tracked: tuple[str, ...] = _TRACKED_PACKAGES) -> dict[str, Any]:
    """Describe the code that ran: Python and the versions of the packages that decide what a detector does.

    ``tracked`` names the packages whose versions matter for the caller (UC-04
    passes its recommender libraries). No git commit: the published repository is
    a tree copy, so a hash proves nothing there; the run folder's own files (corpus
    hashes, package versions, model revisions, predictions) are the provenance.
    """
    packages: dict[str, str] = {}
    for name in tracked:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {"python": platform.python_version(), "packages": packages}


def model_revisions(model_ids: list[str]) -> dict[str, str]:
    """Return the HuggingFace cache revision of each model id, or ``"unknown"``."""
    revisions = {model_id: "unknown" for model_id in model_ids}
    try:
        from huggingface_hub import scan_cache_dir

        for repo in scan_cache_dir().repos:
            if repo.repo_id in revisions:
                revs = sorted(repo.revisions, key=lambda r: r.last_modified, reverse=True)
                if revs:
                    revisions[repo.repo_id] = revs[0].commit_hash
    except Exception:  # noqa: BLE001 — provenance must not break the run
        pass
    return revisions


# ---------------------------------------------------------------------------
# Run folder
# ---------------------------------------------------------------------------


def corpus_tag(identity: dict[str, Any]) -> str:
    """Return the short corpus name used in run-folder names ("model-corpus", "mock-corpus")."""
    cid = str(identity.get("corpus_id") or identity.get("corpus_file") or "corpus")
    cid = (
        cid.replace("uc02-corpus-v2-", "").replace("uc02-pii-corpus", "corpus").replace(".json", "")
    )
    return f"{cid}-corpus" if not cid.endswith("corpus") else cid


def new_run_dir(tag: str, base: Path = RUNS_DIR) -> Path:
    """Create ``<base>/<today>-<tag>/`` (with ``-2``, ``-3`` … if it exists) and return it.

    The tag says what ran on what and how much (date · what · on what · how many),
    e.g. ``detection-table-model-corpus-23-configs``; the runners build it by default.
    """
    stem = f"{_dt.date.today().isoformat()}-{tag}"
    candidate = base / stem
    n = 1
    while candidate.exists():
        n += 1
        candidate = base / f"{stem}-{n}"
    candidate.mkdir(parents=True)
    return candidate


def write_json(path: Path, payload: Any) -> None:
    """Write ``payload`` as UTF-8 JSON with a trailing newline."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_duration(seconds: float) -> str:
    """Return ``"1 min 12 s"``-style text."""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {rest} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


# ---------------------------------------------------------------------------
# Results card
# ---------------------------------------------------------------------------


def write_card(
    run_dir: Path,
    *,
    title: str,
    header: list[tuple[str, str]],
    blocks: list[dict[str, Any]],
    sentence: str,
) -> Path:
    """Write ``RESULTS.md``: a title, a header, one block per configuration, a closing sentence.

    ``header`` is ``[(label, value), …]``; each block is ``{"name": str, "lines":
    [(fact, description), …]}``. The card is meant to be attached as it is: short,
    every number next to the words that say what it means.
    """
    width = max((len(fact) for block in blocks for fact, _ in block["lines"]), default=0)
    out: list[str] = [f"# {title}", ""]
    for label, value in header:
        out.append(f"{label}: {value}")
    out.append("")
    for block in blocks:
        out.append(f"## {block['name']}")
        out.append("")
        for fact, description in block["lines"]:
            out.append(
                f"    {fact.ljust(width)}   ({description})" if description else f"    {fact}"
            )
        out.append("")
    out.append(sentence.strip())
    out.append("")
    path = run_dir / "RESULTS.md"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


__all__ = [
    "RUNS_DIR",
    "code_identity",
    "corpus_identity",
    "corpus_tag",
    "file_sha256",
    "format_duration",
    "model_revisions",
    "new_run_dir",
    "write_card",
    "write_json",
]
