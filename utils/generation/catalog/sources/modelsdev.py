"""Upstream model enrichment (context window, pricing, release dates) from models.dev.

``fetch`` is the one entry point: it gets the models.dev catalog (etag-conditional,
cached between runs), and on any failure falls back first to the LiteLLM pricing
table and then to the last-good cache, so a network hiccup never blocks a catalog
update. The three provider namespaces this module extracts (``openai``,
``anthropic``, ``google``) are enrichment data only — they are folded onto rows the
CLI probes already produced, never used to invent new models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

MODELS_DEV_URL = "https://models.dev/api.json"
LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"


@dataclass
class UpstreamCatalog:
    """One fetch outcome: the enrichment data found, which source supplied it, and when."""

    status: str
    message: str
    provider_models: dict[str, dict[str, Any]]
    source: str
    fetched_at: str
    etag: str | None = None


def fetch(cache_dir: str | Path = ".cache/model-catalog", timeout: int = 30) -> UpstreamCatalog:
    """Fetch the models.dev catalog, falling back to LiteLLM, then the cache, on failure.

    Args:
        cache_dir: Where the fetched body and its etag metadata are cached between runs.
        timeout: Seconds allowed for each HTTP request.

    Returns:
        An ``UpstreamCatalog`` with ``provider_models`` keyed by ``openai``,
        ``anthropic`` and ``google``, and ``source`` naming which path answered
        (``"models.dev"``, ``"litellm"`` or ``"models.dev-cache"``).

    Raises:
        RuntimeError: If models.dev is unreachable, LiteLLM also fails, and no
            cached copy exists to fall back to.
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    body_path = cache / "models.dev.api.json"
    meta_path = cache / "models.dev.meta.json"
    # A corrupt cache or meta file (e.g. a write interrupted mid-flight) must
    # behave like a missing one, or every later offline run is dead until the
    # file is deleted by hand.
    meta = _load_json(meta_path, {})
    cached = _load_json(body_path, None)
    headers = {}
    if meta.get("etag") and cached is not None:
        headers["If-None-Match"] = meta["etag"]
    try:
        resp = requests.get(MODELS_DEV_URL, headers=headers, timeout=timeout)
        if resp.status_code == 304 and cached is not None:
            return UpstreamCatalog(
                "OK",
                "304 not-modified",
                _extract_modelsdev(cached),
                "models.dev",
                _now_from_meta(meta),
                meta.get("etag"),
            )
        resp.raise_for_status()
        data = resp.json()
        _write_text_atomic(body_path, json.dumps(data, sort_keys=True))
        new_meta = {"etag": resp.headers.get("ETag"), "fetched_at": _utc_now()}
        _write_text_atomic(meta_path, json.dumps(new_meta, indent=2, sort_keys=True) + "\n")
        return UpstreamCatalog(
            "OK", "fetched", _extract_modelsdev(data), "models.dev", new_meta["fetched_at"], new_meta["etag"]
        )
    except Exception as exc:
        fallback = _fetch_litellm(timeout)
        if fallback:
            fallback.message = f"UNREACHABLE -> LiteLLM fallback ({exc.__class__.__name__})"
            return fallback
        if cached is not None:
            return UpstreamCatalog(
                "OK",
                f"UNREACHABLE -> kept cached models.dev ({exc.__class__.__name__})",
                _extract_modelsdev(cached),
                "models.dev-cache",
                _now_from_meta(meta),
                meta.get("etag"),
            )
        raise RuntimeError(f"models.dev and LiteLLM unavailable: {exc}") from exc


def _fetch_litellm(timeout: int) -> UpstreamCatalog | None:
    """Fetch and reshape the LiteLLM pricing table into the same provider-namespace shape; None on failure."""
    try:
        resp = requests.get(LITELLM_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 - any litellm failure means "try the next fallback"
        return None
    provider_models = {"openai": {}, "anthropic": {}, "google": {}}
    for model_id, info in data.items():
        if not isinstance(info, dict):
            continue
        provider = _litellm_provider(model_id, info)
        if not provider:
            continue
        provider_models[provider][model_id] = {
            "id": model_id,
            "name": info.get("display_name") or model_id,
            "limit": {
                "context": info.get("max_input_tokens") or info.get("max_tokens"),
                "output": info.get("max_output_tokens"),
            },
            "cost": {
                "input": info.get("input_cost_per_token"),
                "output": info.get("output_cost_per_token"),
            },
        }
    return UpstreamCatalog("OK", "LiteLLM fallback", provider_models, "litellm", _utc_now(), None)


def _extract_modelsdev(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pull the ``openai``/``anthropic``/``google`` model dicts out of the raw models.dev payload."""
    result: dict[str, dict[str, Any]] = {"openai": {}, "anthropic": {}, "google": {}}
    for provider in result:
        entry = data.get(provider, {})
        result[provider] = entry.get("models", {}) if isinstance(entry, dict) else {}
    return result


def _litellm_provider(model_id: str, info: dict[str, Any]) -> str | None:
    """Map a LiteLLM entry to one of ``openai``/``anthropic``/``google``, or None if none matches."""
    provider = str(info.get("litellm_provider") or "")
    if provider == "openai" or model_id.startswith("gpt-"):
        return "openai"
    if provider in {"anthropic", "claude"} or model_id.startswith("claude-"):
        return "anthropic"
    if provider in {"gemini", "vertex_ai", "google"} or model_id.startswith("gemini-"):
        return "google"
    return None


def _load_json(path: Path, default: Any) -> Any:
    """Parse ``path`` as JSON; return ``default`` if it is missing or unparseable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file plus rename, so a crash never leaves a partial file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _now_from_meta(meta: dict[str, Any]) -> str:
    """The cached ``fetched_at`` timestamp, or the current time if the metadata lacks one."""
    return meta.get("fetched_at") or _utc_now()


def _utc_now() -> str:
    """Current UTC time as a second-precision ISO 8601 string with a ``Z`` suffix."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
