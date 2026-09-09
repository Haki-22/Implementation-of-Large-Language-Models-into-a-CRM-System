"""Schema and cross-reference validation for a loaded catalog dict.

``validate_catalog`` first checks ``catalog`` against the JSON Schema at
``schema_path``, then checks the parts a schema alone cannot express: every
alias and every provider's default model must resolve (through the alias
chain) to a model id that actually exists, and every default tier must be
one of the provider's own tier options.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def validate_catalog(catalog: dict, schema_path: str | Path = "data/catalog.schema.json") -> None:
    """Validate ``catalog`` against its JSON Schema and its own alias/default cross-references.

    Args:
        catalog: The loaded catalog dict (see ``load_catalog``).
        schema_path: Path to the catalog's JSON Schema file; callers in this
            package pass the package's own ``SCHEMA_PATH``.

    Raises:
        ValueError: On the first schema violation, or the first alias,
            default-model, or default-tier reference that does not resolve.
    """
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(catalog), key=lambda e: e.path)
    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.path) or "<root>"
        raise ValueError(f"schema error at {path}: {first.message}")
    for provider_name, provider in catalog["providers"].items():
        ids = {m["id"] for m in provider["models"]}
        alias_values = provider.get("aliases", {})
        for alias, target in alias_values.items():
            resolved = _resolve(target, alias_values)
            if resolved not in ids:
                raise ValueError(f"{provider_name} alias {alias!r} resolves to missing model {resolved!r}")
        default = provider["default_model"]
        resolved_default = _resolve(default, alias_values)
        if resolved_default not in ids:
            raise ValueError(
                f"{provider_name} default_model {default!r} resolves to missing model {resolved_default!r}"
            )
        if provider["tier_options"] and provider["default_tier"] not in provider["tier_options"]:
            raise ValueError(f"{provider_name} default_tier {provider['default_tier']!r} is not in tier_options")


def _resolve(value: str, aliases: dict[str, str]) -> str:
    """Follow ``aliases`` from ``value`` until a non-alias id or a cycle is reached."""
    seen = set()
    cur = value
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = aliases[cur]
    return cur
