"""The handoff file: what a run produced, in the shape the database build loads; ``freeze`` makes it the file of record.

Shape (``users`` keyed by the Amazon reviewer id, as the build expects):
``topk_recommendations`` (asin, title, score, reason, evidence_asin, source, grounded),
``topic_clusters`` (label, weight, evidence_titles, _paradigm), ``lifecycle`` (stage),
``absa.aspects`` (aspect, sentiment, evidence, grounded) and ``persona``. The build reads
the first four into ``uc_recommendations``, ``uc_topics`` and ``uc_aspects``; the persona
stays in the file. ``_meta`` names the run, the rule, the prompt version, the provider
and the counts, so the file explains itself without the run folder.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.eval.runs import write_json
from utils.paths import UC04_HANDOFF

SCHEMA = "uc04_to_uc01_handoff v2.0"


def assemble(
    *,
    reviewer_of: dict[int, str],
    reasons: dict[int, list[dict[str, Any]]],
    personas: dict[int, dict[str, Any]],
    aspects: dict[int, dict[str, Any]],
    topics: dict[int, list[dict[str, Any]]],
    lifecycle: dict[int, tuple[str | None, str | None]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Join the pieces into the handoff payload; every linked contact gets a user entry."""
    users: dict[str, dict[str, Any]] = {}
    for cid, rid in sorted(reviewer_of.items()):
        stage, label = lifecycle.get(cid, (None, None))
        entry: dict[str, Any] = {
            "contact_id": cid,
            "topk_recommendations": [
                {
                    "asin": r["asin"],
                    "title": r["title"],
                    "score": r["score"],
                    "reason": r["reason"],
                    "evidence_asin": r["evidence_asin"],
                    "source": r["source"],
                    "grounded": r["grounded"],
                }
                for r in reasons.get(cid, [])
                if r["status"] == "ok"
            ],
            "topic_clusters": topics.get(cid, []),
            "lifecycle": {"stage": stage, "label_cs": label},
            "absa": {"aspects": aspects.get(cid, {}).get("aspects", [])},
        }
        persona = personas.get(cid)
        if persona and persona.get("status") == "ok":
            entry["persona"] = {
                k: persona[k] for k in ("label", "narrative_cs", "tags", "price_segment")
            }
        users[rid] = entry
    return {"_meta": {"schema": SCHEMA, **meta}, "users": users}


def write(run_dir: Path, payload: dict[str, Any]) -> Path:
    """Write the handoff `payload` to `run_dir/handoff.json`; return the path."""
    path = run_dir / "handoff.json"
    write_json(path, payload)
    return path


def freeze(
    run_dir: Path, *, output: Path = UC04_HANDOFF, replace: bool = False
) -> tuple[Path, dict[str, Any]]:
    """Copy the run's handoff to the file the database build loads; refuse to overwrite without ``replace``."""
    source = run_dir / "handoff.json"
    if not source.exists():
        raise FileNotFoundError(f"{run_dir.name} has no handoff.json")
    if output.exists() and not replace:
        raise FileExistsError(
            f"{output} exists (the file of record). Re-run with --replace to make {run_dir.name} the record."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    meta = json.loads(output.read_text(encoding="utf-8"))["_meta"]
    return output, meta


__all__ = ["SCHEMA", "assemble", "freeze", "write"]
