"""Live model listing for the Antigravity CLI (agy).

agy keeps no offline model cache and its backend returns an empty list without
Google OAuth, so the only CLI-truth source is the installed CLI itself:
`agy models` run with the user's existing login. Fallback chain, first success
wins: live listing -> last-good cache in the updater cache dir -> curated
overlay fallback list. Every step logs on the INFO/WARN ladder; nothing here
mutates agy state or sends a prompt to a model.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("catalog.agy")

CACHE_NAME = "agy.models.json"


@dataclass
class AgyModels:
    """One ``read`` outcome: the models found and which source (live/cache/overlay) supplied them."""

    status: str
    message: str
    models: list[dict]
    fetched_at: str | None = None


def _default_runner(args: list[str], timeout: int) -> str:
    """Run ``args`` as a subprocess and return its stdout; raise with stderr on a non-zero exit."""
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:300])
    return proc.stdout


def _parse_json(text: str) -> list[dict]:
    """Parse ``agy models --output-format json`` output into ``{id, display_name}`` rows."""
    data = json.loads(text)
    rows = data.get("models", data) if isinstance(data, dict) else data
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id") or row.get("model") or row.get("name")
        if model_id:
            out.append(
                {
                    "id": model_id,
                    "display_name": row.get("display_name") or row.get("name") or model_id,
                }
            )
    if not out:
        raise ValueError("no models in JSON output")
    return out


def _parse_table(text: str) -> list[dict]:
    """Parse plain-text ``agy models`` table output into ``{id, display_name}`` rows."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("fetching"):
            continue
        parts = line.split("\t") if "\t" in line else line.split(None, 1)
        if parts:
            out.append(
                {
                    "id": parts[0].strip(),
                    "display_name": parts[1].strip() if len(parts) > 1 else parts[0].strip(),
                }
            )
    if not out:
        raise ValueError("no models in table output")
    return out


def read(
    overlay: dict,
    cache_dir: str | Path = ".cache/model-catalog",
    timeout: int = 20,
    runner: Callable[[list[str], int], str] | None = None,
) -> AgyModels:
    """List agy's models, trying live ``agy models``, then the last-good cache, then the overlay.

    Args:
        overlay: The parsed ``overlay.toml``; supplies the binary name and the
            fallback id list under ``providers.agy``.
        cache_dir: Where the last-good listing is cached between runs.
        timeout: Seconds to allow the CLI subprocess before giving up.
        runner: Override for the subprocess call (tests inject a fake here);
            defaults to :func:`_default_runner`.

    Returns:
        An ``AgyModels`` with ``status`` ``"OK"`` (live), ``"CACHED"`` or ``"SKIP"``
        (overlay fallback) according to which source answered.
    """
    cfg = overlay["providers"]["agy"]
    binary = cfg.get("binary", "agy")
    run = runner or _default_runner
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    cache_file = cache / CACHE_NAME

    attempt_live = True
    if runner is None and shutil.which(binary) is None:
        log.info("`%s` not found on PATH (maybe installed differently) -> cache/overlay fallback", binary)
        attempt_live = False

    if attempt_live:
        for args in ([binary, "models", "--output-format", "json"], [binary, "models"]):
            try:
                text = run(args, timeout)
                models = _parse_json(text) if "--output-format" in args else _parse_table(text)
            except Exception as exc:  # noqa: BLE001
                # A CLI build rejecting the probed flag is expected, not a
                # degradation — only real failures deserve a WARN.
                level = logging.INFO if "not defined" in str(exc) else logging.WARNING
                log.log(level, "`%s` failed (%s) -> next fallback", " ".join(args), exc)
                continue
            fetched = _utc_now()
            cache_file.write_text(
                json.dumps({"fetched_at": fetched, "models": models}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return AgyModels("OK", f"{len(models)} models from `agy models` (live)", models, fetched)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            models = data["models"]
            return AgyModels(
                "CACHED",
                f"{len(models)} models from last-good cache",
                models,
                data.get("fetched_at"),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("agy cache unreadable (%s) -> overlay fallback", exc)

    ids = list(cfg.get("fallback_allow", []))
    log.info("agy: using overlay fallback list (%d ids)", len(ids))
    return AgyModels(
        "SKIP",
        f"{len(ids)} models from overlay fallback",
        [{"id": model_id, "display_name": model_id} for model_id in ids],
        None,
    )


def _utc_now() -> str:
    """Current UTC time as a second-precision ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
