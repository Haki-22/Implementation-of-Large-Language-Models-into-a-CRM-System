"""Model catalog behind the CLI adapters in ``utils.generation``.

The three provider CLIs (``codex``, ``claude``, ``agy``) each publish the models
they serve in a different place: Codex writes ``~/.codex/models_cache.json``,
Claude Code compiles its alias map into the binary, and the Antigravity CLI only
answers ``agy models`` behind the user's login. This package turns those mixed
sources into two committed files, so that the adapters never read machine state
at run time:

    catalog.json                 full record: ids, aliases, tiers, vendor default,
                                 upstream enrichment (context window, pricing) and a
                                 per-source status block = provenance of the menu
    ../models.py                 GENERATED Python module holding only what the
                                 adapters need (menus, aliases, tiers, migrations)

Regenerate both with ``python -m utils.generation.catalog update`` on a machine
with the CLIs installed, review the diff, commit. ``python -m utils.generation.catalog``
prints the committed catalog; ``... check`` verifies that ``models.py`` matches
``catalog.json`` (a test does the same). The thesis defaults (which model runs when
a caller names none) live in ``utils/generation/__init__.py``, not here.

Vendored from the author's ``model-catalog`` project (MIT); logic unchanged, paths
made package-relative, the snapshot copies dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PACKAGE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = PACKAGE_DIR / "catalog.json"
SCHEMA_PATH = PACKAGE_DIR / "catalog.schema.json"
OVERLAY_PATH = PACKAGE_DIR / "overlay.toml"
CACHE_DIR = PACKAGE_DIR / ".cache"  # gitignored: models.dev body + etag, claude docs, agy last-good
MODELS_MODULE_PATH = PACKAGE_DIR.parent / "models.py"
UPDATE_COMMAND = "python -m utils.generation.catalog update"

# ---------------------------------------------------------------------------
# Read-only lookups over a loaded catalog
# ---------------------------------------------------------------------------


def load_catalog(path: str | Path | None = None) -> dict:
    """Load ``catalog.json`` (or ``path``). Treat the result as read-only."""
    return json.loads(Path(path or CATALOG_PATH).read_text(encoding="utf-8"))


def list_models(provider: str, catalog: dict | None = None) -> list[dict]:
    """Every model row of ``provider`` (``codex``, ``claude`` or ``agy``) in catalog order.

    Args:
        provider: The provider key as it appears under ``catalog["providers"]``.
        catalog: A pre-loaded catalog dict; defaults to loading ``catalog.json``.

    Returns:
        The provider's ``models`` list, unmodified.
    """
    data = catalog or load_catalog()
    return list(data["providers"][provider]["models"])


def resolve_alias(cli: str, alias: str, catalog: dict | None = None) -> str:
    """Follow the provider's alias chain (``best`` -> ``fable`` -> ``claude-fable-5``)."""
    data = catalog or load_catalog()
    aliases = data["providers"][cli].get("aliases", {})
    cur = alias
    seen = set()
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = aliases[cur]
    return cur


def tiers(model_id: str, catalog: dict | None = None) -> list[str]:
    """The reasoning-effort tiers ``model_id`` supports, searching every provider.

    Args:
        model_id: A model id or one of its aliases.
        catalog: A pre-loaded catalog dict; defaults to loading ``catalog.json``.

    Returns:
        The model's ``tiers`` list.

    Raises:
        KeyError: If no provider's models list contains ``model_id``.
    """
    data = catalog or load_catalog()
    for provider in data["providers"].values():
        for model in provider["models"]:
            if model["id"] == model_id or model_id in model.get("aliases", []):
                return list(model["tiers"])
    raise KeyError(model_id)


def default_model(cli: str, catalog: dict | None = None) -> str:
    """The vendor's menu default for ``cli`` (not the thesis default)."""
    data = catalog or load_catalog()
    return resolve_alias(cli, data["providers"][cli]["default_model"], data)


__all__ = [
    "CACHE_DIR",
    "CATALOG_PATH",
    "MODELS_MODULE_PATH",
    "OVERLAY_PATH",
    "PACKAGE_DIR",
    "SCHEMA_PATH",
    "UPDATE_COMMAND",
    "default_model",
    "list_models",
    "load_catalog",
    "resolve_alias",
    "tiers",
]
