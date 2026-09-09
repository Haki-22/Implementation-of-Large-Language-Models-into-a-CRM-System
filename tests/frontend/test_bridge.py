"""The bridge behind the demo page: every route answers the shape the page reads,
the gated routes fail closed, the registries are served as they are, and a job
runs to completion in the background.

The model-call switch is off for every test; the mock provider is used where a
generation is needed. Tests that read ``substrate.db`` or the run folders skip when
those are absent (a fresh clone before ``build_all``).
"""

from __future__ import annotations

import sys
import time

import pytest
from fastapi.testclient import TestClient

from utils.paths import SUBSTRATE_DB, THESIS_ROOT, UC01_RUNS_DIR

_BRIDGE_DIR = THESIS_ROOT / "thesis-dm-frontend" / "bridge"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import app as bridge_app  # noqa: E402
import jobs  # noqa: E402
import routes_repo  # noqa: E402
from ucs.uc01_personalization import levels, picker  # noqa: E402
from ucs.uc02_pseudonymization.code.ner import NER_BACKENDS  # noqa: E402
from ucs.uc03_mcp_privacy.tools import TOOL_NAMES  # noqa: E402
from ucs.uc04_matchmaker import arms as arm_registry  # noqa: E402
from ucs.uc04_matchmaker.arms import model as model_registry  # noqa: E402
from utils.llm_switch import disable_llm_calls_for_process  # noqa: E402

needs_db = pytest.mark.skipif(not SUBSTRATE_DB.exists(), reason="substrate.db not built")


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A ``TestClient`` over the bridge app with the model-call switch forced off."""
    disable_llm_calls_for_process()
    return TestClient(bridge_app.app)


# ---------------------------------------------------------------------------
# Shell: health, catalog, switch
# ---------------------------------------------------------------------------


def test_health_reports_what_the_page_needs(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["llm_calls_enabled"] is False
    for key in ("substrate_db", "uc01_pick", "uc02_corpus", "uc04_handoff", "dm_frontend"):
        assert key in body


def test_catalog_serves_every_provider_with_thesis_defaults(client: TestClient) -> None:
    body = client.get("/generation/catalog").json()
    ids = [p["id"] for p in body["providers"]]
    assert ids == ["codex", "claude", "agy", "mock"]
    assert body["default_provider"] == "codex"
    codex = next(p for p in body["providers"] if p["id"] == "codex")
    assert codex["thesis_default_model"] == body["default_models"]["codex"]
    assert any(m["id"] == codex["thesis_default_model"] for m in codex["models"])
    claude = next(p for p in body["providers"] if p["id"] == "claude")
    assert "sonnet" in claude["aliases"]
    first = codex["models"][0]
    for key in ("id", "display_name", "tiers", "pricing", "context_window"):
        assert key in first


def test_switch_reads_off_and_gated_routes_fail_closed(client: TestClient) -> None:
    assert client.get("/llm-switch").json()["enabled"] is False
    chat = client.post(
        "/uc03/chat", json={"session": "0" * 8 + "-0000-4000-8000-" + "0" * 12, "message": "ahoj"}
    )
    assert chat.status_code == 403
    gen = client.post(
        "/uc01/generate",
        json={"contact_id": 1, "brief_id": 1, "level": "2", "provider": "codex"},
    )
    assert gen.status_code == 403
    model_run = client.post(
        "/uc04/model-run", json={"methods": ["rerank_als"], "provider": "codex"}
    )
    assert model_run.status_code == 403
    roundtrip = client.post(
        "/uc02/roundtrip", json={"text": "Jan Novák, 602 123 456", "provider": "codex"}
    )
    assert roundtrip.status_code == 403


# ---------------------------------------------------------------------------
# Registries served as they are
# ---------------------------------------------------------------------------


def test_uc01_levels_are_the_ladder(client: TestClient) -> None:
    body = client.get("/uc01/levels").json()
    assert [lvl["id"] for lvl in body["levels"]] == list(levels.LADDER)
    by_id = {lvl["id"]: lvl for lvl in body["levels"]}
    assert by_id["0"]["uses_model"] is False and by_id["6d"]["uses_model"] is True
    assert "pricing" in by_id["6d"]["needs"]
    assert by_id["3a"]["tier"] is False and by_id["3"]["tier"] is True


def test_uc03_tools_are_the_servers_fifteen(client: TestClient) -> None:
    body = client.get("/uc03/tools?profile=strict").json()
    assert [t["name"] for t in body["tools"]] == list(TOOL_NAMES)
    by_name = {t["name"]: t for t in body["tools"]}
    assert by_name["query_sql"]["disabled"] is True
    assert by_name["update_contact"]["held_for_review"] is True
    assert by_name["create_note"]["kind"] == "write"
    assert by_name["search_contacts"]["description"]
    open_profile = client.get("/uc03/tools?profile=open").json()
    assert {t["name"]: t for t in open_profile["tools"]}["query_sql"]["disabled"] is False


def test_uc03_chat_refuses_a_provider_that_cannot_host_mcp(client: TestClient) -> None:
    res = client.post(
        "/uc03/chat",
        json={
            "session": "0" * 8 + "-0000-4000-8000-" + "0" * 12,
            "message": "ahoj",
            "provider": "unsupported",
        },
    )
    assert res.status_code == 400
    assert "unsupported_mcp_provider" in res.json()["detail"]


@pytest.mark.parametrize(
    "provider, model",
    [
        ("codex", "gpt-5.6-luna"),
        ("agy", "gemini-3.8-flash"),
    ],
)
def test_uc03_forwards_selected_model_and_keeps_session_fixed(client, monkeypatch, provider, model):
    import routes_uc03

    calls = []

    async def fake_turn(message, **kwargs):
        calls.append(kwargs)
        return {
            "answer": "Test",
            "profile": kwargs["profile"],
            "model_saw": message,
            "you_said": message,
            "answer_model_view": "Test",
            "tool_calls": [],
            "restoration": {"ok": True},
        }

    monkeypatch.setattr(routes_uc03, "run_turn", fake_turn)
    monkeypatch.setattr(routes_uc03, "require_llm_calls_on", lambda provider: None)
    monkeypatch.setattr(routes_uc03, "scratch_db", lambda: SUBSTRATE_DB)
    settings = {"provider": provider, "model": model, "tier": "low"}
    session = client.post("/uc03/session", json=settings).json()
    assert all(session[key] == value for key, value in settings.items())
    request = {"session": session["session"], "message": "Find a contact", **settings}
    for index in range(2):
        response = client.post("/uc03/chat", json=request)
        assert response.status_code == 200, response.text
        assert response.json()["resumed"] == (index > 0)
    assert calls[1]["provider"] == provider and calls[1]["model"] == model
    assert calls[1]["tier"] == "low" and calls[1]["resume"]
    for changed in ({"provider": "claude"}, {"tier": "high"}, {"model": "gpt-5.6-sol"}):
        response = client.post("/uc03/chat", json={**request, **changed})
        assert response.status_code == 400
    assert len(calls) == 2
    assert client.post("/uc03/session", json={"provider": "mock"}).status_code == 400


def test_uc04_arms_are_the_registries(client: TestClient) -> None:
    body = client.get("/uc04/arms").json()
    assert [a["name"] for a in body["classical"]] == list(arm_registry.ARMS)
    assert [m["name"] for m in body["methods"]] == list(model_registry.MODEL_ARMS)
    slow = {a["name"] for a in body["classical"] if a["slow"]}
    assert slow == set(arm_registry.SLOW)


# ---------------------------------------------------------------------------
# UC-02 without a model
# ---------------------------------------------------------------------------


def test_uc02_mask_and_restore_round_trip_on_rules(client: TestClient) -> None:
    text = "Ozvěte se na jan.novak@firma.cz nebo 602 123 456, IČO 27082440."
    masked = client.post("/uc02/mask", json={"text": text, "use_ner": False}).json()
    assert "<EMAIL_1>" in masked["masked"] and "<PHONE_1>" in masked["masked"]
    assert masked["counts"] == {"EMAIL": 1, "PHONE": 1, "ICO": 1}
    assert masked["ner_backend"] is None
    restored = client.post(
        "/uc02/restore",
        json={"text": masked["masked"], "mapping": masked["mapping"], "original": text},
    ).json()
    assert restored["restored"] == text and restored["exact"] is True


def test_uc02_ner_backends_list_the_registry_with_the_record_f1(client: TestClient) -> None:
    body = client.get("/uc02/ner-backends").json()
    assert [b["backend"] for b in body["backends"]] == list(NER_BACKENDS)
    default = next(b for b in body["backends"] if b["default"])
    assert default["backend"] == body["default"]
    if body["record_run"]:
        assert default["f1"] is not None


def test_uc02_results_lists_run_folders(client: TestClient) -> None:
    body = client.get("/uc02/results").json()
    assert "card" in body and isinstance(body["runs"], list)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def test_job_runs_in_the_background_and_reports_progress(client: TestClient) -> None:
    def target(progress: jobs.ProgressFn) -> dict:
        for i in range(3):
            progress(i + 1, 3, f"step {i + 1}")
        return {"run_dir": "stub"}

    job = jobs.start("test-stub", "stub job", target, total=3)
    for _ in range(50):
        body = client.get(f"/jobs/{job.id}").json()
        if body["state"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert body["state"] == "done"
    assert body["done"] == 3 and body["total"] == 3
    assert body["result"] == {"run_dir": "stub"}
    assert "step 3" in body["log"]
    assert client.get("/jobs").json()["jobs"][0]["id"] == job.id


def test_a_failing_job_reports_its_error(client: TestClient) -> None:
    def target(progress: jobs.ProgressFn) -> dict:
        raise ValueError("boom")

    job = jobs.start("test-fail", "failing job", target)
    for _ in range(50):
        body = client.get(f"/jobs/{job.id}").json()
        if body["state"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert body["state"] == "failed" and "boom" in body["error"]


# ---------------------------------------------------------------------------
# With the database
# ---------------------------------------------------------------------------


@needs_db
def test_uc01_contacts_default_to_the_pick(client: TestClient) -> None:
    pick = picker.load_pick()
    expected = list(pick["reading_set"]) + [i for ids in pick["strata"].values() for i in ids]
    body = client.get("/uc01/contacts").json()
    assert body["scope"] == "pick"
    assert [c["id"] for c in body["contacts"]] == expected
    assert body["contacts"][0]["pick"]["tier"] in ("linked", "prospect")
    search = client.get("/uc01/contacts", params={"q": "Novák", "scope": "all"}).json()
    assert search["scope"] == "all"


@needs_db
def test_uc01_person_card_names_what_each_level_lacks(client: TestClient) -> None:
    pick = picker.load_pick()
    contact_id = pick["reading_set"][0]
    body = client.get(f"/uc01/contacts/{contact_id}").json()
    assert body["id"] == contact_id and body["name"]
    assert set(body["ocean"]) == {"O", "C", "E", "A", "N"}
    assert [lvl["level"] for lvl in body["levels"]] == list(levels.LADDER)
    assert body["levels"][0]["ok"] is True  # level 0 needs nothing
    assert body["pick"]["stratum"] == "reading"


@needs_db
def test_uc01_generate_on_mock_returns_a_judged_message(client: TestClient) -> None:
    pick = picker.load_pick()
    contact_id = pick["reading_set"][0]
    merged = client.post(
        "/uc01/generate",
        json={
            "contact_id": contact_id,
            "brief_id": pick["briefs"][0],
            "level": "1",
            "provider": "mock",
        },
    ).json()
    assert merged["text"] and merged["used_model"] is False
    assert merged["rules"]["accepted"] in (True, False)
    custom = client.post(
        "/uc01/generate",
        json={
            "contact_id": contact_id,
            "custom_template": "Dobrý den, {name_vocative}, máme pro Vás novinku.",
            "level": "2",
            "provider": "mock",
        },
    ).json()
    assert custom["used_model"] is True and custom["brief"]["category"] == "custom"


@needs_db
def test_uc01_runs_and_messages_read_the_folders(client: TestClient) -> None:
    if not UC01_RUNS_DIR.exists():
        pytest.skip("no UC-01 run folders")
    body = client.get("/uc01/runs").json()
    with_messages = [r for r in body["runs"] if r["has_messages"]]
    if not with_messages:
        pytest.skip("no run with messages.jsonl")
    run = with_messages[0]["name"]
    rows = client.get(f"/uc01/runs/{run}/messages", params={"limit": 5}).json()["rows"]
    assert rows and "text" in rows[0] and "system_prompt" not in rows[0]


@needs_db
def test_uc04_customers_and_detail_read_the_record_run(client: TestClient) -> None:
    runs = client.get("/uc04/runs", params={"kind": "arena"}).json()
    if not runs["runs"]:
        pytest.skip("no arena run folder")
    customers = client.get("/uc04/customers").json()
    assert customers["scope"] == "pick" and customers["customers"]
    first = next((c for c in customers["customers"] if c["in_run"]), None)
    if first is None:
        pytest.skip("pick contact not in the record run")
    detail = client.get(f"/uc04/customers/{first['id']}").json()
    assert detail["hidden"]["asin"] == first["hidden"]["asin"]
    assert detail["arms"] and len(detail["arms"][0]["top10"]) <= 10
    run_detail = client.get(f"/uc04/runs/{runs['runs'][0]['name']}").json()
    assert run_detail["kind"] == "arena" and run_detail["rows"]


# ---------------------------------------------------------------------------
# The repository browser
# ---------------------------------------------------------------------------


def test_repo_tree_root_lists_the_tracked_tree(client: TestClient) -> None:
    body = client.get("/repo/tree").json()
    assert body["readme"] == "README.md"
    names = {d["name"] for d in body["dirs"]}
    assert {"ucs", "utils", "substrate", "thesis-dm-frontend"} <= names
    assert body["files"][0]["name"] == "README.md"
    ucs = client.get("/repo/tree", params={"path": "ucs"}).json()
    assert ucs["path"] == "ucs" and ucs["crumbs"] == [{"name": "ucs", "path": "ucs"}]
    assert any(d["name"] == "uc02_pseudonymization" and d["readme"] for d in ucs["dirs"])


def test_repo_file_reads_text_and_refuses_traversal(client: TestClient) -> None:
    readme = client.get("/repo/file", params={"path": "README.md"}).json()
    assert readme["kind"] == "markdown" and readme["content"].startswith("#")
    code = client.get("/repo/file", params={"path": "utils/paths.py"}).json()
    assert code["kind"] == "code" and code["language"] == "python" and code["dir"] == "utils"
    assert client.get("/repo/file", params={"path": "../CLAUDE.md"}).status_code == 400
    assert (
        client.get(
            "/repo/file", params={"path": "thesis-dm-frontend/bridge/.runtime/x"}
        ).status_code
        == 404
    )


def test_repo_search_and_the_explainer_cite_a_tracked_file(client: TestClient) -> None:
    if routes_repo.tracked_source() != "git ls-files":
        pytest.skip("the code search is `git grep`; this tree is not a Git repository")
    hits = client.get("/repo/search", params={"q": "def pseudonymize("}).json()
    assert any(h["path"].endswith("pseudonymizer.py") for h in hits["hits"])
    ask = client.post(
        "/code/ask", json={"question": "co dělá tento soubor", "file_path": "utils/paths.py"}
    ).json()
    assert ask["file"]["path"] == "utils/paths.py" and "   1  " in ask["file"]["snippet"]


# ---------------------------------------------------------------------------
# The installation screen
# ---------------------------------------------------------------------------


def test_setup_status_lists_what_a_clone_lacks(client: TestClient) -> None:
    body = client.get("/setup/status").json()
    assert isinstance(body["ready"], bool)
    ids = [c["id"] for c in body["checks"]]
    assert ids == [
        "packed",
        "database",
        "ner_model",
        "whisper_model",
        "raw_inputs",
        "hf_token",
        "clis",
    ]
    assert body["plans"]["minimal"] == ["unpack", "database", "ner", "whisper"]
    assert set(body["plans"]["full"]) <= set(body["steps"])
    assert client.post("/setup/run", json={"steps": ["nonsense"]}).status_code == 400
    assert client.post("/setup/run", json={"plan": "nonsense"}).status_code == 400


def test_setup_reports_the_hugging_face_token_and_rejects_an_empty_one(client: TestClient) -> None:
    body = client.get("/setup/status").json()
    token = next(c for c in body["checks"] if c["id"] == "hf_token")
    assert token["state"] in ("ok", "info") and "present" in token["detail"]
    assert client.post("/setup/hf-token", json={"token": "  "}).status_code == 400


# ---------------------------------------------------------------------------
# Page history: the thread and the last choices of a tab survive a tab switch and a reload
# ---------------------------------------------------------------------------


def test_history_round_trips_and_deletes(client: TestClient, tmp_path, monkeypatch) -> None:
    import routes_history

    monkeypatch.setattr(routes_history, "HISTORY_DIR", tmp_path)
    assert client.get("/history/uc01").json()["thread"] == []
    thread = [{"role": "user", "text": ["a"]}, {"role": "ai", "html": "<p>b</p>"}]
    put = client.put("/history/uc01", json={"thread": thread, "state": {"contactId": 11}}).json()
    assert put["messages"] == 2
    back = client.get("/history/uc01").json()
    assert back["thread"] == thread
    assert back["state"] == {"contactId": 11}
    assert back["updated"]
    summary = client.get("/history").json()
    assert {t["tab"]: t["messages"] for t in summary["tabs"]}["uc01"] == 2
    assert client.delete("/history/uc01").json()["deleted"] is True
    assert client.get("/history/uc01").json()["thread"] == []
    assert client.get("/history/nope").status_code == 404


def test_history_keeps_only_the_last_turns(client: TestClient, tmp_path, monkeypatch) -> None:
    import routes_history

    monkeypatch.setattr(routes_history, "HISTORY_DIR", tmp_path)
    thread = [{"role": "user", "text": [str(i)]} for i in range(routes_history.MAX_THREAD + 5)]
    put = client.put("/history/uc04", json={"thread": thread}).json()
    assert put["messages"] == routes_history.MAX_THREAD
    assert client.get("/history/uc04").json()["thread"][0]["text"] == ["5"]
    assert client.delete("/history").json()["deleted"] == 1
