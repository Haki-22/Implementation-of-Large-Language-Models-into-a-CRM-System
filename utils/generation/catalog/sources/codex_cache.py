"""Offline model listing for the Codex CLI, read from its own cache file.

Codex writes the menu it last fetched from OpenAI to ``~/.codex/models_cache.json``
on login/refresh, so this source needs no network call of its own: it reads that
file (and ``~/.codex/config.toml`` for the account's personalization, captured but
never merged into the catalog) as CLI-distributed truth. A missing cache (never
logged in) is reported as ``SKIP``, not an error; the merge step then falls back
to the models.dev OpenAI subset.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass
class CodexCache:
    """One read of the local Codex model cache, plus the account settings it must not leak into."""

    status: str
    message: str
    models: list[dict[str, Any]]
    fetched_at: str | None = None
    client_version: str | None = None
    etag: str | None = None
    # Captured but deliberately NOT merged into the catalog (personalization
    # is stripped); they exist so tests can prove that invariant.
    config_default_model: str | None = None
    config_default_tier: str | None = None
    migrations: dict[str, str] | None = None


def read(
    cache_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> CodexCache:
    """Read the local Codex model cache and config file (paths overridable for tests).

    Args:
        cache_path: Override for ``~/.codex/models_cache.json``.
        config_path: Override for ``~/.codex/config.toml``.

    Returns:
        A ``CodexCache`` with ``status`` ``"OK"`` and the visible models when the
        cache exists, or ``"SKIP"`` (with an empty model list) when it does not.
    """
    cache = Path(cache_path or os.path.expanduser("~/.codex/models_cache.json"))
    config = Path(config_path or os.path.expanduser("~/.codex/config.toml"))
    config_data = _read_config(config)
    if not cache.exists():
        return CodexCache(
            status="SKIP",
            message="cache missing (not logged in?) -> using models.dev openai subset",
            models=[],
            config_default_model=config_data.get("model"),
            config_default_tier=config_data.get("model_reasoning_effort"),
            migrations=config_data.get("notice", {}).get("model_migrations", {}),
        )

    with cache.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    models = [m for m in data.get("models", []) if m.get("visibility") == "list"]
    return CodexCache(
        status="OK",
        message=f"{len(models)} models from {_tilde(cache)}",
        models=models,
        fetched_at=data.get("fetched_at"),
        client_version=data.get("client_version"),
        etag=data.get("etag"),
        config_default_model=config_data.get("model"),
        config_default_tier=config_data.get("model_reasoning_effort"),
        migrations=config_data.get("notice", {}).get("model_migrations", {}),
    )


def _tilde(path: Path) -> str:
    """Render ``path`` relative to the home directory as ``~/...``, or unchanged if it is not under it."""
    # The message is published in the catalog's sources block; never leak the
    # OS username through an absolute home path.
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _read_config(path: Path) -> dict[str, Any]:
    """Parse the Codex TOML config file; an empty dict when it does not exist."""
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)
