"""The page's independently selected judge: routing and switch, without live providers."""

from types import SimpleNamespace
import json

import pytest
from fastapi.testclient import TestClient

from tests.frontend.test_bridge import bridge_app, disable_llm_calls_for_process

import routes_uc01


@pytest.fixture
def client():
    """A ``TestClient`` over the bridge app with the model-call switch forced off."""
    disable_llm_calls_for_process()
    return TestClient(bridge_app.app)


@pytest.mark.parametrize("endpoint", ["generate", "ladder"])
def test_model_judge_is_gated_even_for_a_model_free_writer(client, endpoint):
    request = {
        "contact_id": 1,
        "provider": "mock",
        "level": "0",
        "levels": "0",
        "custom_template": "Dobrý den.",
        "judge": {"provider": "codex", "model": "gpt-5.6-luna", "tier": "low"},
    }
    assert client.post(f"/uc01/{endpoint}", json=request).status_code == 403
    request["judge"]["provider"] = "claude"
    assert client.post(f"/uc01/{endpoint}", json=request).status_code == 400


def test_selected_judge_is_independent_and_rules_remain_first(client, monkeypatch):
    calls = []
    gates = []

    async def fake_generate(*args, **kwargs):
        calls.append(("writer", kwargs))
        return SimpleNamespace(
            ok=True, text="Dobrý den.", to_dict=lambda: {"text": "Dobrý den."}
        )

    async def fake_judge(text, contact, cascade):
        calls.append(("judge", cascade.to_dict()))
        return SimpleNamespace(to_dict=lambda: {"final": "VALID", "calls": 1})

    monkeypatch.setattr(routes_uc01, "require_llm_calls_on", gates.append)
    monkeypatch.setattr(routes_uc01, "generate", fake_generate)
    monkeypatch.setattr(routes_uc01.judge, "judge_cascade", fake_judge)
    monkeypatch.setattr(
        routes_uc01.data, "connect", lambda: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(routes_uc01.data, "load_contact", lambda *args: object())
    choice = {"provider": "agy", "model": "gemini-3.8-flash", "tier": "high"}
    response = client.post(
        "/uc01/generate",
        json={
            "contact_id": 1,
            "level": "0",
            "provider": "mock",
            "custom_template": "Dobrý den.",
            "judge": choice,
        },
    )
    assert response.status_code == 200, response.text
    assert gates == ["agy"]
    assert calls[0][1]["provider"] == "mock" and calls[0][1]["judges"] == ("rules",)
    assert calls[1][1]["judges"] == [choice]
    assert response.json()["judge_config"]["judges"] == [choice]
    assert response.json()["judgment"]["final"] == "VALID"


def test_ladder_judges_after_generation_in_its_own_folder(
    client, monkeypatch, tmp_path
):
    folder = tmp_path / "page-test"
    folder.mkdir()
    judged = folder / "judge-test"
    judged.mkdir()
    trail = {"level": "0", "text": "test", "final": "PARTIAL", "judges": []}
    (judged / "verdicts.jsonl").write_text(json.dumps(trail) + "\n")
    calls = []

    def fake_generate(*args, **kwargs):
        calls.append(("writer", kwargs))
        return folder

    def fake_judge(run_id, cascade, **kwargs):
        calls.append(("judge", run_id, cascade.to_dict(), kwargs))
        return judged

    result = {}

    def immediate_job(kind, label, target):
        result.update(target(lambda *args: None))
        return SimpleNamespace(to_dict=lambda: {"id": "test-job"})

    monkeypatch.setattr(routes_uc01, "require_llm_calls_on", lambda provider: None)
    monkeypatch.setattr(routes_uc01, "db_one", lambda *args: {"id": 1})
    monkeypatch.setattr(routes_uc01, "_pick", lambda: {})
    monkeypatch.setattr(routes_uc01.card, "ladder_runs", lambda: [])
    monkeypatch.setattr(routes_uc01.runner, "run", fake_generate)
    monkeypatch.setattr(
        routes_uc01.judge_run, "load_run_messages", lambda folder: [{"text": "test"}]
    )
    monkeypatch.setattr(routes_uc01.judge_run, "judge_run", fake_judge)
    monkeypatch.setattr(routes_uc01.jobs, "start", immediate_job)
    choice = {"provider": "codex", "model": "gpt-5.6-luna", "tier": "low"}
    response = client.post(
        "/uc01/ladder",
        json={
            "contact_id": 1,
            "levels": "0",
            "provider": "mock",
            "judge": choice,
        },
    )
    assert response.status_code == 200, response.text
    assert [call[0] for call in calls] == ["writer", "judge"]
    assert calls[1][1] == folder.name and calls[1][2]["judges"] == [choice]
    assert calls[1][3]["runs_dir"] == tmp_path
    assert result["judgment"]["folder"] == "page-test/judge-test"
    assert result["judgment"]["rows"] == [trail]


def test_claude_model_cannot_be_selected_through_agy(client):
    choice = {"provider": "agy", "model": "claude-sonnet-4-6-thinking", "tier": "low"}
    response = client.post(
        "/uc01/generate",
        json={
            "contact_id": 1,
            "level": "0",
            "provider": "mock",
            "custom_template": "test",
            "judge": choice,
        },
    )
    assert response.status_code == 400
    assert "judge_model" in response.text


def cascade_choice(level=3):
    """Independent configurations for both providers and a higher-effort arbiter."""
    return {
        "level": level,
        "judges": [
            {"provider": "codex", "model": "gpt-5.6-luna", "tier": "low"},
            {"provider": "agy", "model": "gemini-3.8-flash", "tier": "low"},
        ][: 1 if level == 1 else 2],
        "arbiter": {"provider": "codex", "model": "gpt-5.6-luna", "tier": "high"}
        if level == 3
        else None,
    }


@pytest.mark.parametrize("level", [1, 2, 3])
def test_each_cascade_role_keeps_its_selected_model_and_tier(monkeypatch, level):
    gates = []
    monkeypatch.setattr(routes_uc01, "require_llm_calls_on", gates.append)
    choice = cascade_choice(level)
    cascade = routes_uc01._selected_judge(routes_uc01.JudgeChoice(**choice))
    actual = cascade.to_dict()
    assert {key: actual[key] for key in choice} == choice
    assert gates == [spec["provider"] for spec in choice["judges"]] + (
        ["codex"] if level == 3 else []
    )


@pytest.mark.parametrize("role", ["first", "second", "arbiter"])
def test_claude_is_rejected_in_every_judge_role_before_any_call(
    client, monkeypatch, role
):
    monkeypatch.setattr(
        routes_uc01, "generate", lambda *a, **kw: pytest.fail("writer called")
    )
    choice = cascade_choice()
    selected = (
        choice["arbiter"]
        if role == "arbiter"
        else choice["judges"][0 if role == "first" else 1]
    )
    selected.update(provider="claude", model="sonnet")
    response = client.post(
        "/uc01/generate",
        json={
            "contact_id": 1,
            "level": "0",
            "provider": "mock",
            "custom_template": "test",
            "judge": choice,
        },
    )
    assert response.status_code == 400
    assert "judge_provider" in response.text


@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_cascade_level_respects_the_model_call_switch(client, level):
    response = client.post(
        "/uc01/generate",
        json={
            "contact_id": 1,
            "level": "0",
            "provider": "mock",
            "custom_template": "test",
            "judge": cascade_choice(level),
        },
    )
    assert response.status_code == 403


def test_rules_only_configuration_never_requires_model_permission(monkeypatch):
    monkeypatch.setattr(
        routes_uc01, "require_llm_calls_on", lambda *a: pytest.fail("model gate called")
    )
    assert routes_uc01._selected_judge(routes_uc01.JudgeChoice(level=0)) is None


@pytest.mark.parametrize(
    "change", ["same_providers", "missing_arbiter", "extra_arbiter", "missing_judge"]
)
def test_invalid_cascade_is_rejected_before_generation(client, change):
    choice = cascade_choice()
    if change == "same_providers":
        choice["judges"][1] = choice["judges"][0]
    elif change == "missing_arbiter":
        choice["arbiter"] = None
    elif change == "extra_arbiter":
        choice["level"] = 2
    else:
        choice["judges"] = choice["judges"][:1]
    response = client.post(
        "/uc01/generate",
        json={
            "contact_id": 1,
            "level": "0",
            "provider": "mock",
            "custom_template": "test",
            "judge": choice,
        },
    )
    assert response.status_code == 400
