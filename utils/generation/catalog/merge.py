"""Merge the overlay config, upstream enrichment, and each CLI's live probe into ``catalog.json``.

``build_catalog`` is the single entry point: it takes the overlay (``overlay.toml``,
the human-curated allow/deny lists and defaults), the upstream models.dev snapshot
(context windows, pricing, release dates), and one probe result per provider CLI
(the codex model cache, the Claude alias map plus its docs-derived default, and the
``agy models`` listing), and produces the three provider blocks that make up the
committed catalog. Per-provider assembly (``_build_codex``, ``_build_claude``,
``_build_agy``) differs in how each CLI exposes its menu, but all three end in the
same row shape (``_model_row``) so the generated ``models.py`` can treat every
provider uniformly.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("catalog.merge")

_TIER_RE = re.compile(r"^(?P<base>.+)-(?P<tier>low|medium|high)$")
_TIER_ORDER = ["low", "medium", "high"]
_DISPLAY_TIER_RE = re.compile(r"\s*\((Low|Medium|High)\)\s*$")

# Enrichment namespaces to try, in order, for agy-served ids (agy routes
# non-Gemini models too, so the base id may live in any of these).
_AGY_ENRICH_NAMESPACES = ("google", "anthropic", "openai")


def build_catalog(
    overlay: dict,
    upstream: Any,
    codex: Any,
    claude_aliases: Any,
    agy: Any,
    claude_default: Any = None,
) -> dict:
    """Assemble the full catalog dict: per-provider model rows plus a source provenance block.

    Args:
        overlay: The parsed ``overlay.toml`` (human-curated allow/deny lists and defaults).
        upstream: The models.dev snapshot result (``source``, ``status``, ``message``,
            ``etag``, ``fetched_at``, ``provider_models``).
        codex: The codex model-cache probe result.
        claude_aliases: The Claude binary's extracted alias map probe result.
        agy: The ``agy models`` probe result.
        claude_default: The Claude vendor-docs default probe result, or None when
            that source was not attempted.

    Returns:
        A dict with ``schema_version``, ``generated_at``, a ``sources`` block
        recording each input's status, and ``providers`` (the ``codex``, ``claude``
        and ``agy`` blocks from ``_build_codex``/``_build_claude``/``_build_agy``).
    """
    generated_at = _utc_now()
    providers = {
        "codex": _build_codex(overlay, upstream, codex),
        "claude": _build_claude(overlay, upstream, claude_aliases, claude_default),
        "agy": _build_agy(overlay, upstream, agy),
    }
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "sources": {
            "overlay": {"version": overlay.get("overlay", {}).get("version")},
            "models.dev": {
                "source": upstream.source,
                "status": upstream.status,
                "message": upstream.message,
                "etag": upstream.etag,
                "fetched_at": upstream.fetched_at,
            },
            "codex": {
                "status": codex.status,
                "message": codex.message,
                "fetched_at": codex.fetched_at,
                "client_version": codex.client_version,
                "etag": codex.etag,
            },
            "claude": {"status": claude_aliases.status, "message": claude_aliases.message},
            "claude-docs": {
                "status": getattr(claude_default, "status", "SKIP"),
                "message": getattr(claude_default, "message", "not attempted"),
                "fetched_at": getattr(claude_default, "fetched_at", None),
            },
            "agy": {"status": agy.status, "message": agy.message, "fetched_at": agy.fetched_at},
        },
        "providers": providers,
    }


def fold_agy_ids(models: list[dict]) -> list[dict]:
    """Fold tier-suffixed agy ids into base models with reasoning tiers.

    Ids ending in -low/-medium/-high group by base id; anything else (for
    example `claude-opus-4-6-thinking` — "thinking" is not a tier) passes
    through as a standalone row with no tiers. Per-model default tier prefers
    medium, then high, then low, because some families ship without a medium
    variant.
    """
    families: dict[str, dict] = {}
    order: list[tuple[str, Any]] = []
    for model in models:
        match = _TIER_RE.match(model["id"])
        if match:
            base, tier = match.group("base"), match.group("tier")
            family = families.get(base)
            if family is None:
                family = {"tiers": [], "display": _DISPLAY_TIER_RE.sub("", model["display_name"])}
                families[base] = family
                order.append(("family", base))
            if tier not in family["tiers"]:
                family["tiers"].append(tier)
        else:
            order.append(("solo", model))
    rows = []
    for kind, item in order:
        if kind == "family":
            family = families[item]
            tiers = [t for t in _TIER_ORDER if t in family["tiers"]]
            default_tier = next((t for t in ("medium", "high", "low") if t in tiers), "")
            rows.append(
                {
                    "id": item,
                    "display_name": family["display"],
                    "tiers": tiers,
                    "default_tier": default_tier,
                }
            )
        else:
            rows.append(
                {
                    "id": item["id"],
                    "display_name": item["display_name"],
                    "tiers": [],
                    "default_tier": "",
                }
            )
    return rows


def _build_codex(overlay: dict, upstream: Any, codex: Any) -> dict:
    """Build the ``codex`` provider block from its model cache, or the overlay fallback list."""
    cfg = overlay["providers"]["codex"]
    openai = upstream.provider_models.get("openai", {})
    rows = []
    if codex.models:
        for model in codex.models:
            model_id = model["slug"]
            rows.append(
                _model_row(
                    model_id,
                    upstream_model=openai.get(model_id, {}),
                    display_name=model.get("display_name") or model_id,
                    tiers=[
                        x.get("effort")
                        for x in model.get("supported_reasoning_levels", [])
                        if x.get("effort")
                    ],
                    default_tier=model.get("default_reasoning_level") or "",
                    source="codex-cache+models.dev",
                    fetched_at=codex.fetched_at or upstream.fetched_at,
                    migration=(model.get("upgrade") or {}).get("model")
                    or (codex.migrations or {}).get(model_id),
                )
            )
    else:
        for model_id in cfg.get("fallback_allow", []):
            up = openai.get(model_id, {})
            rows.append(
                _model_row(
                    model_id,
                    upstream_model=up,
                    display_name=up.get("name") or model_id,
                    tiers=_efforts(up),
                    default_tier=cfg.get("default_tier", ""),
                    source=upstream.source,
                    fetched_at=upstream.fetched_at,
                )
            )
    rows = [r for r in rows if r["id"] not in set(cfg.get("deny", []))]
    tier_options = _ordered_unique(t for r in rows for t in r["tiers"])
    # Vendor-recommended default: the cache lists the menu top-first, so the
    # first offered row is what the vendor pushes. The overlay value is only
    # the fallback for when the cache is unavailable.
    default = rows[0]["id"] if codex.models and rows else cfg["default_model"]
    return {
        "cli": cfg["cli"],
        "binary": cfg["binary"],
        "default_model": _safe_default(default, {}, rows),
        "default_tier": _safe_tier(cfg.get("default_tier", ""), tier_options),
        "tier_options": tier_options,
        "model_string_format": cfg.get("model_string_format", "{model} {tier}"),
        "aliases": {},
        "models": rows,
        **_dispatch(cfg),
    }


def _build_claude(
    overlay: dict, upstream: Any, claude_aliases: Any, claude_default: Any = None
) -> dict:
    """Build the ``claude`` provider block from the overlay allow list plus the binary's aliases."""
    cfg = overlay["providers"]["claude"]
    anthropic = upstream.provider_models.get("anthropic", {})
    aliases = dict(cfg.get("aliases", {}))
    source = "overlay+models.dev"
    if getattr(claude_aliases, "status", "SKIP") == "OK":
        aliases.update(claude_aliases.aliases)
        source = "claude-binary+overlay+models.dev"
    aliases_by_id: dict[str, set] = {}
    for alias, target in aliases.items():
        concrete = _resolve_alias_chain(target, aliases)
        if concrete.startswith("claude-"):
            aliases_by_id.setdefault(concrete, set()).add(alias)
    model_ids = list(cfg.get("allow", []))
    for target in aliases.values():
        concrete = _resolve_alias_chain(target, aliases)
        if concrete.startswith("claude-") and concrete not in model_ids:
            model_ids.append(concrete)
    rows = []
    for model_id in model_ids:
        base = _strip_1m(model_id)
        up = anthropic.get(model_id) or anthropic.get(base) or {}
        aliases_for_model = sorted(
            aliases_by_id.get(model_id, set()) | aliases_by_id.get(base, set())
        )
        rows.append(
            _model_row(
                model_id,
                upstream_model=up,
                display_name=(up.get("name") or model_id)
                + (" [1M]" if model_id.endswith("[1m]") else ""),
                aliases=aliases_for_model,
                tiers=cfg.get("effort_tiers", []),
                default_tier=cfg.get("default_tier", ""),
                source=source,
                fetched_at=upstream.fetched_at,
                context_override=1_000_000 if model_id.endswith("[1m]") else None,
            )
        )
    # Vendor-recommended default: the official docs disclose what `default`
    # resolves to per account type (parsed by sources/claude_docs.py); the
    # overlay value is the fallback when that source is SKIP.
    default = cfg["default_model"]
    if getattr(claude_default, "status", "SKIP") == "OK" and getattr(
        claude_default, "model_id", None
    ):
        default = claude_default.model_id
    return {
        "cli": cfg["cli"],
        "binary": cfg["binary"],
        "default_model": _safe_default(default, aliases, rows),
        "default_tier": _safe_tier(cfg.get("default_tier", ""), cfg.get("effort_tiers", [])),
        "tier_options": cfg.get("effort_tiers", []),
        "aliases": aliases,
        "models": rows,
        **_dispatch(cfg),
    }


def _build_agy(overlay: dict, upstream: Any, agy: Any) -> dict:
    """Build the ``agy`` provider block from ``agy models``, folding tier-suffixed ids together."""
    cfg = overlay["providers"]["agy"]
    rows = []
    for folded in fold_agy_ids(agy.models):
        up = {}
        for namespace in _AGY_ENRICH_NAMESPACES:
            up = upstream.provider_models.get(namespace, {}).get(folded["id"], {})
            if up:
                break
        rows.append(
            _model_row(
                folded["id"],
                upstream_model=up,
                display_name=folded["display_name"] or up.get("name") or folded["id"],
                tiers=folded["tiers"],
                default_tier=folded["default_tier"],
                source=f"agy-{agy.status.lower()}+models.dev",
                fetched_at=agy.fetched_at or upstream.fetched_at,
            )
        )
    tier_options = _ordered_unique(t for r in rows for t in r["tiers"])
    # Vendor-recommended default: `agy models` lists the menu top-first (the
    # overlay fallback list keeps the same order), so the first folded row is
    # the recommendation; the overlay value guards the empty-rows edge only.
    default = rows[0]["id"] if rows else cfg["default_model"]
    return {
        "cli": cfg["cli"],
        "binary": cfg["binary"],
        "default_model": _safe_default(default, {}, rows),
        "default_tier": _safe_tier(cfg.get("default_tier", ""), tier_options),
        "tier_options": tier_options,
        "model_string_format": cfg.get("model_string_format", "{model}-{tier}"),
        "aliases": {},
        "models": rows,
        **_dispatch(cfg),
    }


def _safe_default(default: str, aliases: dict[str, str], rows: list[dict]) -> str:
    """Return ``default`` if it resolves to a row in ``rows``, else the first row's id (with a warning)."""
    ids = [row["id"] for row in rows]
    if not ids:
        raise ValueError("no models to choose a default from")
    resolved = _resolve_alias_chain(default, aliases)
    if resolved in ids:
        return default
    log.warning("default model %r is not in the generated menu -> using %r", default, ids[0])
    return ids[0]


def _safe_tier(default_tier: str, tier_options: list[str]) -> str:
    """Return ``default_tier`` if it is one of ``tier_options``, else a sensible fallback tier."""
    if not tier_options:
        return ""
    if default_tier in tier_options:
        return default_tier
    fallback = next((t for t in ("medium", "high", "low") if t in tier_options), tier_options[0])
    log.warning(
        "default tier %r is not in tier options %s -> using %r",
        default_tier,
        tier_options,
        fallback,
    )
    return fallback


def _model_row(
    model_id: str,
    upstream_model: dict[str, Any],
    display_name: str,
    tiers: list[str] | None = None,
    default_tier: str = "",
    source: str = "",
    fetched_at: str = "",
    aliases: list[str] | None = None,
    migration: str | None = None,
    context_override: int | None = None,
) -> dict:
    """Build one catalog model row, folding upstream enrichment onto the CLI's own fields."""
    limit = upstream_model.get("limit", {}) if isinstance(upstream_model, dict) else {}
    return {
        "id": model_id,
        "display_name": display_name,
        "aliases": aliases or [],
        "tiers": _ordered_unique(_efforts(upstream_model) if tiers is None else tiers),
        "default_tier": default_tier,
        "context_window": context_override
        if context_override is not None
        else limit.get("context"),
        "output_tokens": limit.get("output"),
        "knowledge": upstream_model.get("knowledge"),
        "release_date": upstream_model.get("release_date"),
        "last_updated": upstream_model.get("last_updated"),
        "pricing": upstream_model.get("cost"),
        "modalities": upstream_model.get("modalities"),
        "visible": True,
        "deprecated": bool(upstream_model.get("deprecated")),
        "migration": migration,
        "source": source,
        "fetched_at": fetched_at,
    }


def _efforts(model: dict[str, Any]) -> list[str]:
    """The reasoning-effort values a models.dev model entry advertises (``none`` excluded)."""
    out = []
    for opt in model.get("reasoning_options", []) if isinstance(model, dict) else []:
        if opt.get("type") == "effort":
            out.extend(opt.get("values", []))
    return [x for x in out if x != "none"]


def _resolve_alias_chain(value: str, aliases: dict[str, str]) -> str:
    """Follow ``aliases`` from ``value`` until a non-alias id or a cycle is reached."""
    seen = set()
    cur = value
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = aliases[cur]
    return cur


def _strip_1m(model_id: str) -> str:
    """Drop the trailing ``[1m]`` (1M-context) suffix from a Claude model id."""
    return model_id.removesuffix("[1m]")


def _ordered_unique(values) -> list[str]:
    """The truthy values of ``values``, deduplicated, in first-seen order."""
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _utc_now() -> str:
    """Current UTC time as a second-precision ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dispatch(cfg: dict) -> dict:
    """Return ``{"dispatch": …}`` when the overlay carries a dispatch block for the provider."""
    block = cfg.get("dispatch")
    return {"dispatch": dict(block)} if block else {}
