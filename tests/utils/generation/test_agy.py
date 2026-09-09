"""Offline tests for the agy adapter: argv shape, tier folding, envelope parsing."""

from __future__ import annotations

import json

import pytest

from utils.generation import DEFAULT_MODELS
from utils.generation import agy
from utils.generation import models as menus
from utils.generation.errors import (
    GenerationError,
    ProviderAuthError,
    ProviderJsonError,
)

DEFAULT = DEFAULT_MODELS["agy"]


def _tierless_model() -> str | None:
    return next((m for m, t in menus.AGY_TIERS.items() if not t), None)


def test_build_args_folds_tier_into_model_id() -> None:
    args = agy._build_args("hello", model=None, tier="low", timeout=30)
    assert args[:3] == ["agy", "-p", "hello"]
    assert args[args.index("--model") + 1] == f"{DEFAULT}-low"
    assert args[args.index("--output-format") + 1] == "json"
    assert args[args.index("--print-timeout") + 1] == "30s"
    assert "--json-schema" not in args
    assert "--dangerously-skip-permissions" not in args


def test_suffixed_model_id_wins_over_tier_argument() -> None:
    args = agy._build_args("x", model=f"{DEFAULT}-high", tier="low", timeout=5)
    assert args[args.index("--model") + 1] == f"{DEFAULT}-high"


def test_tierless_model_ignores_tier() -> None:
    model = _tierless_model()
    if model is None:
        pytest.skip("the current agy menu has no tier-less model")
    args = agy._build_args("x", model=model, tier="low", timeout=5)
    assert args[args.index("--model") + 1] == model


def test_bad_tier_for_tiered_model_is_refused() -> None:
    with pytest.raises(ValueError, match="Unsupported agy tier"):
        agy._build_args("x", model=DEFAULT, tier="ultra", timeout=5)


def test_schema_goes_through_native_flag() -> None:
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    args = agy._build_args("x", model=None, tier=None, timeout=5, schema=schema)
    assert json.loads(args[args.index("--json-schema") + 1]) == schema


def test_oversized_prompt_is_refused_before_spawning() -> None:
    with pytest.raises(GenerationError, match="command line only"):
        agy._build_args("x" * (agy._ARGV_SINGLE_LIMIT + 1), model=None, tier=None, timeout=5)


def test_native_system_prompt_is_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        agy._build_prompt("p", "s", "native")
    assert agy._build_prompt("p", "s", "concat") == "s\n\np"


# The envelope agy 1.1.26 printed on the live smoke of 2026-09-04 (usage trimmed).
LIVE_ENVELOPE = (
    '{"conversation_id":"a18c10ae","status":"SUCCESS","response":"{\\"ok\\": true}\\n",'
    '"duration_seconds":1.6,"num_turns":1,"usage":{"input_tokens":5819,"output_tokens":198}}'
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (LIVE_ENVELOPE, '{"ok": true}'),
        ('{"result": "OK "}', "OK"),
        ('{"response": {"text": "OK"}}', "OK"),
        ("plain text answer", "plain text answer"),
        ("[1, 2]", "[1, 2]"),
    ],
)
def test_text_from_envelope_is_tolerant(raw: str, expected: str) -> None:
    text, _ = agy._text_from_envelope(raw)
    assert text == expected


def test_envelope_error_is_classified() -> None:
    with pytest.raises(ProviderAuthError):
        agy._text_from_envelope('{"error": "not authenticated: run agy to sign in"}')


def test_envelope_non_success_status_is_an_error() -> None:
    with pytest.raises(GenerationError, match="status=FAILED"):
        agy._text_from_envelope('{"status": "FAILED", "response": "quota exceeded for today"}')


@pytest.mark.asyncio
async def test_generate_json_reads_live_structured_output_shape(monkeypatch) -> None:
    """With --json-schema agy adds `structured_output` next to `response` (live 2026-09-04)."""

    async def fake_run(args, timeout):
        return json.dumps(
            {
                "status": "SUCCESS",
                "response": '{"greeting":"Dobrý den","ok":true,"toolAction":"Completing task"}\n',
                "structured_output": {"greeting": "Dobrý den", "ok": True},
                "json_schema": {"type": "object"},
            }
        )

    monkeypatch.setattr(agy, "_run_agy", fake_run)
    assert await agy.generate_json("p", {"type": "object"}) == {"greeting": "Dobrý den", "ok": True}


@pytest.mark.asyncio
async def test_generate_json_prefers_structured_field(monkeypatch) -> None:
    async def fake_run(args, timeout):
        return json.dumps({"result": "ignored", "structured_output": {"ok": True}})

    monkeypatch.setattr(agy, "_run_agy", fake_run)
    result = await agy.generate_json("p", {"type": "object"})
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_generate_json_parses_fenced_text(monkeypatch) -> None:
    async def fake_run(args, timeout):
        return json.dumps({"result": '```json\n{"ok": true}\n```'})

    monkeypatch.setattr(agy, "_run_agy", fake_run)
    assert await agy.generate_json("p", {"type": "object"}) == {"ok": True}


@pytest.mark.asyncio
async def test_generate_json_rejects_non_object(monkeypatch) -> None:
    async def fake_run(args, timeout):
        return json.dumps({"result": "no json here"})

    monkeypatch.setattr(agy, "_run_agy", fake_run)
    with pytest.raises(ProviderJsonError):
        await agy.generate_json("p", {"type": "object"})
