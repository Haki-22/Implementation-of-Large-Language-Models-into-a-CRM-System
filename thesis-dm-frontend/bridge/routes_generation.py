"""Generation routes: the model catalog the settings tab is built from, the short menus,
and the process-wide model-call switch.

The catalog is ``utils/generation/catalog/catalog.json`` as ``models.py`` was generated
from it; the page types nothing about models itself.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from utils.generation import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER,
    DEFAULT_TIER,
    PROVIDERS,
    cli_status,
    list_options,
)
from utils.generation.catalog import load_catalog
from utils.llm_switch import (
    disable_llm_calls_for_process,
    enable_llm_calls_for_process,
    llm_calls_source,
)

router = APIRouter()

_MODEL_FIELDS = (
    "id",
    "display_name",
    "tiers",
    "default_tier",
    "pricing",
    "context_window",
    "output_tokens",
    "release_date",
    "knowledge",
    "deprecated",
    "aliases",
    "modalities",
)


# ---------------------------------------------------------------------------
# Catalog and menus
# ---------------------------------------------------------------------------


@router.get("/generation/options")
def generation_options() -> dict[str, Any]:
    """The short menus: providers, models, tiers, defaults and CLI status."""
    return list_options()


@router.get("/generation/catalog")
def generation_catalog() -> dict[str, Any]:
    """Every provider and model the generation layer knows, with prices and limits.

    Built from the committed catalog; the thesis defaults and the CLI status are added
    so the settings tab can mark what runs on this machine.
    """
    catalog = load_catalog()
    status = cli_status()
    providers: list[dict[str, Any]] = []
    for name in PROVIDERS:
        entry = catalog.get("providers", {}).get(name)
        if entry is None:
            # The mock provider is not in the catalog: it is built in.
            providers.append(
                {
                    "id": name,
                    "cli": None,
                    "default_model": DEFAULT_MODELS.get(name),
                    "default_tier": None,
                    "thesis_default_model": DEFAULT_MODELS.get(name),
                    "aliases": {},
                    "installed": status.get(name, {}).get("available", False),
                    "cli_status": status.get(name),
                    "models": [
                        {
                            "id": "mock",
                            "display_name": "Mock (offline)",
                            "tiers": [],
                            "deprecated": False,
                        }
                    ],
                }
            )
            continue
        providers.append(
            {
                "id": name,
                "cli": entry.get("cli"),
                "default_model": entry.get("default_model"),
                "default_tier": entry.get("default_tier"),
                "thesis_default_model": DEFAULT_MODELS.get(name),
                "aliases": entry.get("aliases", {}),
                "model_string_format": entry.get("model_string_format"),
                "installed": status.get(name, {}).get("available", False),
                "cli_status": status.get(name),
                "models": [
                    {key: model.get(key) for key in _MODEL_FIELDS}
                    for model in entry.get("models", [])
                ],
            }
        )
    return {
        "generated_at": catalog.get("generated_at"),
        "schema_version": catalog.get("schema_version"),
        "sources": catalog.get("sources", {}),
        "default_provider": DEFAULT_PROVIDER,
        "default_tier": DEFAULT_TIER,
        "default_models": dict(DEFAULT_MODELS),
        "providers": providers,
    }


# ---------------------------------------------------------------------------
# The model-call switch
# ---------------------------------------------------------------------------


class LlmSwitchRequest(BaseModel):
    """Flip the process-wide model-call switch from the browser."""

    enabled: bool


def llm_switch_state() -> dict[str, Any]:
    """Whether model calls are on for this bridge process, and why."""
    enabled, source = llm_calls_source()
    return {"enabled": enabled, "source": source, "variable": "THESIS_LLM_CALLS"}


@router.get("/llm-switch")
def llm_switch_get() -> dict[str, Any]:
    """Return whether model calls are switched on for this bridge process, and why."""
    return llm_switch_state()


@router.post("/llm-switch")
def llm_switch_set(req: LlmSwitchRequest) -> dict[str, Any]:
    """Switch model calls on or off for this bridge process (does not edit .env)."""
    if req.enabled:
        enable_llm_calls_for_process()
    else:
        disable_llm_calls_for_process()
    return llm_switch_state()
