"""
Command-line smoke tester for `utils.generation`.

This module is intentionally small.  It lets a developer test the shared
generation API directly:

    python -m utils.generation.cli --provider mock --prompt "Say OK"
    python -m utils.generation.cli --provider codex --model <model> --prompt "Say OK"
    python -m utils.generation.cli --list-options
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from utils.generation import DEFAULT_PROVIDER, DEFAULT_TIER, PROVIDERS, generate, list_options
from utils.llm_switch import add_force_llm_argument, apply_force_llm


def _load_schema(schema_arg: str | None) -> dict[str, Any] | None:
    """
    Load a JSON Schema from an inline JSON string or a file path.

    Args:
        schema_arg: None, a JSON object string, or a path to a JSON file.

    Returns:
        Parsed JSON Schema dict, or None when no schema was supplied.

    Raises:
        ValueError: If the schema is not valid JSON or is not a JSON object.
    """
    if schema_arg is None:
        return None

    possible_path = Path(schema_arg)
    if possible_path.exists():
        raw = possible_path.read_text(encoding="utf-8")
    else:
        raw = schema_arg

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--schema must be a JSON object or a path to a JSON object file")
    return parsed


async def _run(args: argparse.Namespace) -> None:
    """Execute one generation call and print text or formatted JSON."""
    if args.list_options:
        print(json.dumps(list_options(), ensure_ascii=False, indent=2))
        return

    if not args.prompt:
        raise ValueError("--prompt is required unless --list-options is used")

    schema = _load_schema(args.schema)
    result = await generate(
        args.prompt,
        schema=schema,
        provider=args.provider,
        system_prompt=args.system_prompt,
        model=args.model,
        tier=args.tier,
        retries=args.retries,
    )

    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the generation smoke-test CLI."""
    parser = argparse.ArgumentParser(description="Test utils.generation directly.")
    add_force_llm_argument(parser)
    parser.add_argument("--list-options", action="store_true", help="Print provider/model options.")
    parser.add_argument("--prompt", default=None, help="Prompt to send to the selected provider.")
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        choices=list(PROVIDERS),
        help=f"Provider to use (default: {DEFAULT_PROVIDER}).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model id or alias from the generated menu. Examples: sonnet, gemini-3.8-flash.",
    )
    parser.add_argument(
        "--tier",
        default=DEFAULT_TIER,
        help=(
            "Reasoning tier. Codex: per model (gpt-5.5: low..xhigh). "
            "Claude: low/medium/high/xhigh/max. agy: low/medium/high (ignored by tier-less models)."
        ),
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="Optional system instruction. Uses concat mode for provider portability.",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Optional JSON Schema as inline JSON or path to a JSON file.",
    )
    parser.add_argument("--retries", type=int, default=0, help="Retries after first failure.")
    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    apply_force_llm(args)
    try:
        asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - CLI should show a concise error.
        print(f"generation error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
