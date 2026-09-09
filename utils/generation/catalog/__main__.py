"""Command line of the model catalog: ``show`` (default), ``update``, ``check``.

    python -m utils.generation.catalog            # print the committed catalog
    python -m utils.generation.catalog update     # regenerate catalog.json + models.py
    python -m utils.generation.catalog check      # exit 1 if models.py is stale or
                                                  # catalog.json fails its schema

``update`` reads the local CLI state (Codex cache file, Claude binary, live
``agy models``) plus the public models.dev feed, validates the result, and writes
``catalog.json`` and the generated ``utils/generation/models.py`` atomically. Any
failure keeps both files as they were (last-good). A provider whose CLI is not on
this machine keeps its rows from the committed catalog and is marked KEPT in the
sources block, so regenerating on a partial machine never erases a provider.
No model is ever prompted; ``agy models`` and ``claude auth status`` are listings.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from utils.generation.catalog import (
    CACHE_DIR,
    CATALOG_PATH,
    MODELS_MODULE_PATH,
    OVERLAY_PATH,
    SCHEMA_PATH,
    load_catalog,
    resolve_alias,
)
from utils.generation.catalog.codegen import models_module_is_current, write_models_module
from utils.generation.catalog.detect import detect_installed_providers
from utils.generation.catalog.merge import build_catalog
from utils.generation.catalog.sources import (
    agy_models,
    claude_binary,
    claude_docs,
    codex_cache,
    modelsdev,
)
from utils.generation.catalog.validate import validate_catalog

log = logging.getLogger("catalog")

FRESHNESS_WARN_DAYS = 14

# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def update(
    overlay_path: Path = OVERLAY_PATH,
    catalog_path: Path = CATALOG_PATH,
    schema_path: Path = SCHEMA_PATH,
    models_path: Path = MODELS_MODULE_PATH,
    cache_dir: Path = CACHE_DIR,
) -> int:
    """Regenerate ``catalog.json`` and ``models.py``; keep last-good on any failure."""
    try:
        with open(overlay_path, "rb") as fh:
            overlay = tomllib.load(fh)
        upstream = modelsdev.fetch(cache_dir)
        codex = codex_cache.read()
        claude_bin = overlay["providers"]["claude"].get("binary", "claude")
        claude = claude_binary.read(binary=claude_bin)
        claude_default = claude_docs.read(binary=claude_bin, cache_dir=cache_dir)
        agy = agy_models.read(overlay, cache_dir=cache_dir)

        catalog = build_catalog(overlay, upstream, codex, claude, agy, claude_default)
        old_text = catalog_path.read_text(encoding="utf-8") if catalog_path.exists() else ""
        previous = json.loads(old_text) if old_text else {}
        installed = detect_installed_providers(overlay.get("providers", {}))
        present, kept, absent = keep_or_drop_uninstalled(catalog, previous, installed)
        _require_providers(present)
        # Validate AFTER the drop so the file written to disk is exactly what
        # passed validation.
        validate_catalog(catalog, schema_path)

        if old_text and _same_catalog_ignoring_audit_timestamps(old_text, catalog):
            new_text, changed_count, catalog_written = old_text, 0, False
        else:
            new_text = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
            changed_count = _changed_count(old_text, catalog)
            _write_atomic(catalog_path, new_text)
            catalog_written = True
        models_written = write_models_module(json.loads(new_text), models_path)

        total = sum(len(p["models"]) for p in catalog["providers"].values())
        _print_status(codex, claude, agy, upstream, total)
        print(f"claude-docs: {claude_default.status:<6} {claude_default.message}")
        print(f"detected   : installed CLIs -> {', '.join(present) or '(none)'}")
        if kept:
            print(
                f"kept       : CLI not on PATH, rows kept from the committed catalog -> {', '.join(kept)}"
            )
        if absent:
            print(
                f"skipped    : not installed and not in the committed catalog -> {', '.join(absent)}"
            )
        for level, line in freshness_lines(_freshness_sources(codex, agy, upstream)):
            log.log(logging.WARNING if level == "WARN" else logging.INFO, "freshness: %s", line)
        print(
            f"models.py  : {'OK     regenerated' if models_written else 'OK     already current'} {models_path}"
        )
        if catalog_written:
            print(f"UPDATED ({total} models, {changed_count} changed) {catalog_path}")
        else:
            print("NO CHANGE")
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level fail-safe: keep last-good outputs on any error
        log.error("catalog update failed: %s", exc)
        print(f"FAILED: {exc} (catalog.json and models.py unchanged)")
        return 1


def keep_or_drop_uninstalled(
    catalog: dict, previous: dict, installed: dict[str, bool]
) -> tuple[list[str], list[str], list[str]]:
    """Resolve providers whose CLI is absent here; mutates ``catalog`` in place.

    A provider present in the committed catalog keeps those rows (status KEPT);
    one never catalogued is dropped. Returns (present, kept, absent) names.
    """
    present: list[str] = []
    kept: list[str] = []
    absent: list[str] = []
    prev_providers = previous.get("providers", {}) if previous else {}
    for name in list(catalog["providers"]):
        if installed.get(name):
            present.append(name)
        elif name in prev_providers:
            catalog["providers"][name] = prev_providers[name]
            binary = prev_providers[name].get("binary", name)
            catalog["sources"][name] = {
                "status": "KEPT",
                "message": (
                    f"`{binary}` not on PATH here; rows kept from the catalog generated "
                    f"{previous.get('generated_at', '?')}"
                ),
            }
            present.append(name)
            kept.append(name)
        else:
            del catalog["providers"][name]
            absent.append(name)
    return present, kept, absent


def _require_providers(present: list[str]) -> None:
    """Raise a clear error when no provider survived detection, instead of a raw schema error."""
    # Without this, an empty provider set surfaces as a raw JSON Schema error
    # ("providers: {} should be non-empty") instead of the actual cause.
    if not present:
        raise RuntimeError(
            "no supported CLIs detected on PATH (codex, claude, agy) and no committed catalog to keep"
        )


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file plus rename, so a crash never leaves a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def freshness_lines(
    sources: dict[str, str | None], now: datetime | None = None
) -> list[tuple[str, str]]:
    """Report the age of each timestamped source; WARN past FRESHNESS_WARN_DAYS."""
    now = now or datetime.now(timezone.utc)
    out: list[tuple[str, str]] = []
    for name, stamp in sources.items():
        if not stamp:
            out.append(("INFO", f"{name}: no timestamp"))
            continue
        try:
            age = (now - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).days
        except ValueError:
            out.append(("INFO", f"{name}: unreadable timestamp {stamp!r}"))
            continue
        out.append(("WARN" if age > FRESHNESS_WARN_DAYS else "INFO", f"{name}: {age}d old"))
    return out


def _freshness_sources(codex, agy, upstream) -> dict[str, str | None]:
    """The timestamped sources ``freshness_lines`` should report on, by name."""
    return {
        "codex cache": codex.fetched_at,
        "agy models": agy.fetched_at,
        "models.dev": upstream.fetched_at,
    }


def _print_status(codex, claude, agy, upstream, total: int) -> None:
    """Print each source's status/message line plus the overall validation summary."""
    print(f"codex      : {codex.status:<6} {codex.message}")
    print(f"claude     : {claude.status:<6} {claude.message}")
    print(f"agy        : {agy.status:<6} {agy.message}")
    print(f"models.dev : {upstream.status:<6} {upstream.message}")
    print(f"validate   : OK     catalog valid ({total} models)")


def _changed_count(old_text: str, new_catalog: dict) -> int:
    """Count model rows whose semantic content (ignoring audit timestamps) actually changed."""
    if not old_text:
        return sum(len(p["models"]) for p in new_catalog["providers"].values())
    try:
        old = json.loads(old_text)
    except json.JSONDecodeError:
        return sum(len(p["models"]) for p in new_catalog["providers"].values())
    count = 0
    for provider, pdata in new_catalog["providers"].items():
        old_models = {
            m["id"]: _strip_audit_timestamps(m)
            for m in old.get("providers", {}).get(provider, {}).get("models", [])
        }
        for model in pdata["models"]:
            if old_models.get(model["id"]) != _strip_audit_timestamps(model):
                count += 1
    return count


def _same_catalog_ignoring_audit_timestamps(old_text: str, new_catalog: dict) -> bool:
    """True if the old and new catalogs are identical once audit-only fields are stripped."""
    try:
        old = json.loads(old_text)
    except json.JSONDecodeError:
        return False
    return _semantic_view(old) == _semantic_view(new_catalog)


def _semantic_view(catalog: dict):
    """The catalog with its audit trail (``sources`` block, timestamps) stripped, for comparison."""
    # The `sources` block is an audit trail (statuses, messages, etags), not
    # catalog semantics — a models.dev "fetched" vs "304 not-modified" run must
    # not count as a changed catalog.
    trimmed = {k: v for k, v in catalog.items() if k != "sources"}
    return _strip_audit_timestamps(trimmed)


def _strip_audit_timestamps(value):
    """Recursively drop ``generated_at``/``fetched_at``/``source`` keys (audit fields, not catalog data)."""
    # Model-row `source` strings embed fetch status (agy-ok vs agy-cached,
    # models.dev vs models.dev-cache): provenance audit, not catalog data.
    if isinstance(value, dict):
        return {
            k: _strip_audit_timestamps(v)
            for k, v in value.items()
            if k not in {"generated_at", "fetched_at", "source"}
        }
    if isinstance(value, list):
        return [_strip_audit_timestamps(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# show / check
# ---------------------------------------------------------------------------


def show(catalog_path: Path = CATALOG_PATH) -> int:
    """Print the committed catalog in a form a reader can check against the CLIs."""
    catalog = load_catalog(catalog_path)
    print(f"catalog    : {catalog_path}")
    print(f"generated  : {catalog['generated_at']}  (schema {catalog['schema_version']})")
    for name, info in sorted(catalog.get("sources", {}).items()):
        if isinstance(info, dict) and "status" in info:
            print(f"  source {name:<12} {info['status']:<6} {info.get('message', '')}")
    for name, provider in catalog["providers"].items():
        vendor_default = resolve_alias(name, provider["default_model"], catalog)
        print(
            f"\n{name} (`{provider['binary']}`)  vendor default: {vendor_default}  tier: {provider['default_tier'] or '-'}"
        )
        for row in provider["models"]:
            tiers = "/".join(row["tiers"]) or "-"
            flags = []
            if row.get("deprecated"):
                flags.append("deprecated")
            if row.get("migration"):
                flags.append(f"-> {row['migration']}")
            if row.get("aliases"):
                flags.append("aliases: " + ", ".join(row["aliases"]))
            print(f"  {row['id']:<28} tiers {tiers:<28} {' '.join(flags)}")
        if provider.get("aliases"):
            print("  aliases: " + ", ".join(f"{k}={v}" for k, v in provider["aliases"].items()))
    return 0


def check(
    catalog_path: Path = CATALOG_PATH,
    schema_path: Path = SCHEMA_PATH,
    models_path: Path = MODELS_MODULE_PATH,
) -> int:
    """Exit 0 when catalog.json validates and models.py is its exact rendering."""
    catalog = load_catalog(catalog_path)
    validate_catalog(catalog, schema_path)
    print(f"catalog.json: OK valid ({catalog['generated_at']})")
    if models_module_is_current(catalog, models_path):
        print("models.py   : OK current")
        return 0
    print(
        "models.py   : STALE - run `python -m utils.generation.catalog update` (or `--render-only`)"
    )
    return 1


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: dispatch to ``show`` (default), ``update`` or ``check``.

    Args:
        argv: Arguments to parse instead of ``sys.argv[1:]`` (mainly for tests).

    Returns:
        The process exit code: 0 on success, 1 on a failed update or a stale/
        invalid catalog under ``check``.
    """
    parser = argparse.ArgumentParser(
        prog="python -m utils.generation.catalog",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("show", help="Print the committed catalog (default).")
    p_update = sub.add_parser(
        "update", help="Regenerate catalog.json and models.py from this machine's CLIs."
    )
    p_update.add_argument(
        "--cache-dir", default=str(CACHE_DIR), help="Network caches (models.dev, claude docs, agy)."
    )
    p_update.add_argument(
        "--render-only",
        action="store_true",
        help="Only re-render models.py from the committed catalog.json (no CLI or network reads).",
    )
    p_update.add_argument(
        "--quiet", action="store_true", help="Silence INFO logging (WARN and above only)."
    )
    sub.add_parser("check", help="Validate catalog.json and verify models.py is current.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING if getattr(args, "quiet", False) else logging.INFO,
        format="%(levelname)-5s %(message)s",
    )
    if args.command == "update":
        if args.render_only:
            changed = write_models_module(load_catalog(), MODELS_MODULE_PATH)
            print(
                f"models.py: {'regenerated' if changed else 'already current'} {MODELS_MODULE_PATH}"
            )
            return 0
        return update(cache_dir=Path(args.cache_dir))
    if args.command == "check":
        return check()
    return show()


if __name__ == "__main__":
    raise SystemExit(main())
