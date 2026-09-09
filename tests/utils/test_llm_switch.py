"""Tests for the global model-call switch (utils.llm_switch) and its enforcement in the adapters."""

from __future__ import annotations

import asyncio

import pytest

from utils import llm_switch
from utils.generation.errors import LLMCallsDisabledError


@pytest.fixture
def no_env(monkeypatch, tmp_path):
    """Neither the process env nor a .env file sets the switch."""
    monkeypatch.delenv(llm_switch.ENV_VAR, raising=False)
    return tmp_path / ".env"


def test_default_is_off(no_env):
    assert llm_switch.llm_calls_source(no_env) == (False, "default")
    assert llm_switch.llm_calls_enabled(no_env) is False


def test_dotenv_turns_it_on_and_env_overrides(no_env, monkeypatch):
    no_env.write_text("# demo\nTHESIS_LLM_CALLS=TRUE\nOTHER=1\n", encoding="utf-8")
    assert llm_switch.llm_calls_source(no_env) == (True, ".env")

    monkeypatch.setenv(llm_switch.ENV_VAR, "false")
    assert llm_switch.llm_calls_source(no_env) == (False, "env")


def test_dotenv_parser_strips_quotes_and_ignores_garbage(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=\"x y\"\n\n# c\nnot-a-pair\nB='z'\n", encoding="utf-8")
    assert llm_switch.read_dotenv(path) == {"A": "x y", "B": "z"}
    assert llm_switch.read_dotenv(tmp_path / "missing") == {}


def test_unrecognised_value_falls_through_to_default(no_env, monkeypatch):
    monkeypatch.setenv(llm_switch.ENV_VAR, "maybe")
    assert llm_switch.llm_calls_source(no_env) == (False, "default")


def test_require_raises_with_hint_and_mock_is_exempt(no_env):
    with pytest.raises(LLMCallsDisabledError) as exc:
        llm_switch.require_llm_calls("codex", no_env)
    assert "--force-llm" in str(exc.value)
    llm_switch.require_llm_calls("mock", no_env)  # never raises


def test_force_llm_flag_enables_for_process(no_env, monkeypatch):
    import argparse

    parser = argparse.ArgumentParser()
    llm_switch.add_force_llm_argument(parser)
    assert llm_switch.apply_force_llm(parser.parse_args([])) is False
    assert llm_switch.apply_force_llm(parser.parse_args(["--force-llm"])) is True
    assert llm_switch.llm_calls_source(no_env) == (True, "env")


@pytest.mark.parametrize("provider", ["codex", "claude", "agy"])
def test_adapters_fail_closed_before_any_subprocess(provider, monkeypatch, no_env):
    """With the switch off, no provider adapter ever starts a subprocess."""
    from utils.generation import generate_text

    monkeypatch.setattr(llm_switch, "DOTENV_PATH", no_env)

    async def boom(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("subprocess started although LLM calls are off")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)

    with pytest.raises(LLMCallsDisabledError):
        asyncio.run(generate_text("Say OK", provider=provider, retries=2))


def test_mock_provider_works_with_switch_off(no_env, monkeypatch):
    from utils.generation import generate_text

    monkeypatch.setattr(llm_switch, "DOTENV_PATH", no_env)
    assert asyncio.run(generate_text("Say OK", provider="mock"))


def test_status_cli_prints_state(capsys, no_env, monkeypatch):
    monkeypatch.setattr(llm_switch, "DOTENV_PATH", no_env)
    assert llm_switch.main([]) == 0
    assert "LLM calls: OFF" in capsys.readouterr().out


def test_codex_prompt_transport_switches_to_stdin_above_the_argument_limit():
    from utils.generation.codex import MAX_ARG_PROMPT_BYTES, prompt_transport

    assert prompt_transport("short") == ("short", None)
    long = "x" * (MAX_ARG_PROMPT_BYTES + 1)
    assert prompt_transport(long) == ("-", long)
