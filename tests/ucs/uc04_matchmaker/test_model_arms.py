"""UC-04 model methods: the strict parser, the seeded shuffle, the run folder, the pairing and the reuse, offline.

Runs on a toy substrate with the mock provider (which returns the candidates in the
order the prompt lists them). What must never go wrong: an unknown or repeated id
fails a call and a short answer is partial with the rest appended in prompt order;
the shuffle is seeded per customer and does not leave the hidden item last; every
call is recorded verbatim with its provenance fields; the re-rank method fed the
ALS order back unchanged scores exactly like ALS (zero discordant pairs); the top-200
method calls only the customers whose hidden item ALS reached; ``--reuse`` takes the
records over instead of calling; the registry table names every method once.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from ucs.uc04_matchmaker import attachment, card, model_arena, sample
from ucs.uc04_matchmaker.arms import ARMS
from ucs.uc04_matchmaker.arms.model import MODEL_ARMS, _calls, _prompts, resolve
from ucs.uc04_matchmaker.arms.model import describe_and_retrieve, rerank_als_with_profile
from ucs.uc04_matchmaker.data import connect

PRODUCTS = [
    ("P1", "Cable", "Kabel USB"),
    ("P2", "Mouse", "Myš bezdrátová"),
    ("P3", "Keyboard", "Klávesnice"),
    ("P4", "Monitor", None),
    ("P5", "Headset", "Sluchátka"),
    ("P6", "Webcam", "Webkamera"),
    ("P7", "Speaker", "Reproduktor"),
    ("P8", "Charger", "Nabíječka"),
    ("P9", "Dock", "Dokovací stanice"),
    ("P10", "Lamp", "Lampa"),
]
CUSTOMERS = [
    (
        1,
        "A",
        [
            ("P1", 5, "2013-01-01"),
            ("P2", 4, "2013-02-01"),
            ("P3", 5, "2013-03-01"),
            ("P4", 3, "2013-04-01"),
        ],
    ),
    (
        2,
        "A",
        [
            ("P1", 4, "2013-01-05"),
            ("P2", 5, "2013-02-05"),
            ("P4", 4, "2013-03-05"),
            ("P5", 5, "2013-03-06"),
        ],
    ),
    (3, "B", [("P2", 5, "2013-01-10"), ("P3", 4, "2013-02-10"), ("P6", 2, "2013-05-10")]),
    (4, "C", [("P1", 3, "2013-01-15"), ("P4", 4, "2013-02-15"), ("P7", 4, "2013-03-15")]),
    (5, "A", [("P3", 3, "2013-01-15"), ("P5", 4, "2013-02-15"), ("P8", 4, "2013-03-15")]),
]


@pytest.fixture()
def toy_db(tmp_path: Path) -> Path:
    """A five-customer, eight-product SQLite file with topics/aspects seeded for customer 1."""
    path = tmp_path / "substrate.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE uc_contacts (id INTEGER PRIMARY KEY, reviewer_id TEXT, amazon_group TEXT,
                                  lifecycle_stage TEXT, ocean JSON, ocean_source TEXT);
        CREATE TABLE uc_lifecycle_stages (code TEXT PRIMARY KEY, label_cs TEXT, label_en TEXT);
        CREATE TABLE uc_products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, name_cs TEXT, category TEXT, description TEXT, price REAL);
        CREATE TABLE uc_reviews (id INTEGER PRIMARY KEY, contact_id INTEGER, product_id INTEGER, rating REAL,
                                 review_date TEXT, summary_en TEXT, text_en TEXT, summary_cs TEXT, text_cs TEXT);
        CREATE TABLE uc_topics (id INTEGER PRIMARY KEY, contact_id INTEGER, rank INTEGER, label TEXT, weight REAL, evidence_titles TEXT, paradigm TEXT);
        CREATE TABLE uc_aspects (id INTEGER PRIMARY KEY, contact_id INTEGER, aspect TEXT, sentiment TEXT, evidence TEXT);
        INSERT INTO uc_lifecycle_stages VALUES ('active', 'aktivní zákazník', 'active');
        INSERT INTO uc_topics VALUES (1, 1, 1, 'computers / myš', 0.5, '[]', 'lda');
        INSERT INTO uc_aspects VALUES (1, 1, 'zvuk', 'positive', 'zvuk je čistý');
        """
    )
    for i, (sku, name, name_cs) in enumerate(PRODUCTS, start=1):
        conn.execute(
            "INSERT INTO uc_products VALUES (?,?,?,?,?,?,?)",
            (i, sku, name, name_cs, "Accessories", f"A {name.lower()}", 9.9),
        )
    rid = 0
    for cid, group, reviews in CUSTOMERS:
        ocean = json.dumps({"O": 4.1, "C": 3.9, "E": 3.2, "A": 3.6, "N": 2.4}) if cid == 1 else None
        conn.execute(
            "INSERT INTO uc_contacts VALUES (?,?,?,?,?,?)",
            (cid, f"R{cid}", group, "active", ocean, "inferred" if ocean else None),
        )
        for sku, rating, day in reviews:
            rid += 1
            pid = [p for p, _, _ in PRODUCTS].index(sku) + 1
            conn.execute(
                "INSERT INTO uc_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, cid, pid, rating, day, "ok", f"english {sku}", "ok cs", f"cesky {sku}"),
            )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def toy_sample(toy_db: Path, tmp_path: Path) -> tuple[str, Path]:
    """Build and write a 4-customer sample (2/1/1 per group) over ``toy_db``; return its name and base dir."""
    conn = connect(toy_db)
    try:
        built = sample.build_sample(
            conn, pick=None, pick_name=None, name="toy-4", quotas={"A": 2, "B": 1, "C": 1}
        )
    finally:
        conn.close()
    base = tmp_path / "samples"
    sample.write_sample(built, base=base)
    return "toy-4", base


@pytest.fixture(autouse=True)
def fake_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """No sentence-transformers in the test: deterministic unit vectors for products and lines."""

    def item_vectors(arena):
        """Deterministic unit vectors, one per item in ``arena``, seeded independently of query text."""
        rng = np.random.default_rng(1)
        v = rng.normal(size=(arena.n_items, 8)).astype(np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def query_vectors(texts):
        """Deterministic unit vectors, one per line in ``texts``, seeded by how many there are."""
        rng = np.random.default_rng(len(texts))
        v = rng.normal(size=(len(texts), 8)).astype(np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    monkeypatch.setattr(describe_and_retrieve, "item_vectors", item_vectors)
    monkeypatch.setattr(describe_and_retrieve, "query_vectors", query_vectors)


# ---------------------------------------------------------------------------
# Parser, shuffle, prompt
# ---------------------------------------------------------------------------


def test_parser_is_strict_and_completes_partial_answers() -> None:
    ids = ["C001", "C002", "C003", "C004"]
    assert _calls.parse_ranking({"ranking": ["C003", "C001", "C004", "C002"]}, ids) == (
        ["C003", "C001", "C004", "C002"],
        "ok",
        [],
        "",
    )
    ranking, status, missing, _ = _calls.parse_ranking({"ranking": ["C004", "C002"]}, ids)
    assert (ranking, status, missing) == (
        ["C004", "C002", "C001", "C003"],
        "partial",
        ["C001", "C003"],
    )
    assert _calls.parse_ranking({"ranking": ["C001", "C001"]}, ids)[1] == "failed"
    assert _calls.parse_ranking({"ranking": ["C001", "C999"]}, ids)[1] == "failed"
    assert _calls.parse_ranking({"other": []}, ids)[1] == "failed"


def test_shuffle_is_seeded_per_customer_and_moves_the_hidden_item() -> None:
    cand = list(range(101))  # the sampler appends the hidden item last
    a = _calls.shuffled(cand, seed=42, contact_id=7)
    assert a == _calls.shuffled(cand, seed=42, contact_id=7)
    assert a != _calls.shuffled(cand, seed=42, contact_id=8)
    assert sorted(a) == cand
    positions = [_calls.shuffled(cand, seed=42, contact_id=c).index(100) for c in range(1, 30)]
    assert len(set(positions)) > 5 and positions.count(100) < 5


def test_prompt_has_both_languages_and_the_schema_allows_a_short_answer() -> None:
    en = _prompts.user_prompt(
        "en", contact_id=3, history_lines=["- 2013-01-01 ★5 Cable"], candidate_lines=["C001  Mouse"]
    )
    cs = _prompts.user_prompt(
        "cs",
        contact_id=3,
        history_lines=["- 2013-01-01 ★5 Kabel"],
        candidate_lines=["C001  Myš"],
        als_order=True,
    )
    assert "Customer C-3" in en and "in random order" in en and en.endswith("Return the JSON.")
    assert "Zákazník Z-3" in cs and "v pořadí modelu ALS" in cs and cs.endswith("Vrať JSON.")
    schema = _prompts.ranking_schema(101)
    assert schema["properties"]["ranking"]["maxItems"] == 101
    assert schema["properties"]["ranking"]["minItems"] == 1
    assert set(_prompts.RANKING_SYSTEM) == set(_prompts.DESCRIBE_SYSTEM) == {"en", "cs"}
    for lang in ("en", "cs"):
        full = _prompts.system_text("ranking", lang, als_order=True, profile=True)
        assert full.endswith(_prompts.NO_TOOLS[lang])
        assert _prompts.ALS_ORDER_ADDENDUM[lang] in full and _prompts.PROFILE_ADDENDUM[lang] in full
        assert _prompts.system_text("describe", lang).endswith(_prompts.NO_TOOLS[lang])
    with pytest.raises(ValueError):
        _prompts.system_text("describe", "en", als_order=True)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def test_mock_run_writes_the_folder_and_the_rerank_equals_als(
    toy_db: Path, toy_sample: tuple[str, Path], tmp_path: Path
) -> None:
    name, base = toy_sample
    run_dir = model_arena.run(
        methods="all",
        sample_name=name,
        langs=["en", "cs"],
        provider="mock",
        n_neg=3,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        samples_dir=base,
        attachments_dir=tmp_path / "attachments",
    )
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert set(config["methods"]) == set(MODEL_ARMS)
    assert config["prompt_version"] == _prompts.PROMPT_VERSION and config["provider"] == "mock"
    assert (run_dir / "sample.json").exists() and (run_dir / "TABLE.md").exists()
    assert (run_dir / "RESULTS.md").exists() and (run_dir / "pairs.json").exists()
    # every call recorded verbatim with its provenance
    call = json.loads(
        next((run_dir / "calls" / "rank_candidates-en-mock").glob("*.json")).read_text()
    )
    for key in (
        "prompt",
        "system_prompt",
        "raw",
        "status",
        "seconds",
        "model",
        "tier",
        "prompt_version",
        "database_sha256",
        "candidates",
        "held_out",
    ):
        assert key in call
    assert call["status"] == "ok" and len(call["ranking"]) == 4  # 3 negatives + the hidden item
    assert "ASIN" not in call["prompt"] and "P1" not in call["prompt"].split("Candidates")[
        1
    ].replace("C00", "")
    # the mock echoes the prompt order: the ALS re-rank scores exactly like ALS
    pairs = json.loads((run_dir / "pairs.json").read_text(encoding="utf-8"))
    rerank = [p for p in pairs if p["method"] == "rerank_als" and p["versus"] == "als_cf"]
    assert rerank and all(
        p["difference"] == 0 and p["only_first"] == p["only_second"] == 0 for p in rerank
    )
    scores = json.loads((run_dir / "scores" / "rerank_als-en.json").read_text(encoding="utf-8"))
    assert scores["calls"] == {
        "ok": 4,
        "partial": 0,
        "failed": 0,
        "reused": 0,
        "hidden_dropped": 0,
    }
    assert scores["protocols"]["sampled"]["n_customers"] == 4
    # the top-200 method calls only the reachable customers and scores under the full protocol
    top = json.loads((run_dir / "scores" / "rerank_als_top200-en.json").read_text(encoding="utf-8"))
    assert list(top["protocols"]) == ["full"]
    assert set(top["customers"]) == set(
        config["methods"]["rerank_als_top200"]["extras"]["reachable"]
    )
    # the describe method scores the whole catalogue under both protocols and keeps its lines
    desc = json.loads(
        (run_dir / "scores" / "describe_and_retrieve-cs.json").read_text(encoding="utf-8")
    )
    assert set(desc["protocols"]) == {"full", "sampled"}
    assert all(len(v) == 3 for v in desc["extras"]["sentences"].values())
    # the profile method records which fields each customer had
    fields = config["methods"]["rerank_als_with_profile"]["extras"]["profile_fields"]
    others = [k for k in fields if k != "1"]
    assert set(fields["1"]) >= {"ocean", "lifecycle", "topics", "aspects"}
    assert others and all("ocean" not in fields[k] for k in others)
    profile_call = json.loads(
        (run_dir / "calls" / "rerank_als_with_profile-cs-mock" / "1.json").read_text()
    )
    assert (
        "Big Five (1–5): O 4,1" in profile_call["prompt"]
        and "aktivní zákazník" in profile_call["prompt"]
    )
    # mock runs neither touch the appendix nor the runs README
    assert (
        not (tmp_path / "attachments").exists() and not (tmp_path / "runs" / "README.md").exists()
    )
    assert (
        attachment.record_model_runs(tmp_path / "runs") == {}
    )  # a mock folder is never the record
    # the appendix pair can be built from explicitly named folders, one per method
    written = attachment.build_model_methods(run_dirs=[run_dir], out_dir=tmp_path / "att")
    csv_text = (tmp_path / "att" / "uc04-model-methods.csv").read_text(encoding="utf-8")
    md_text = (tmp_path / "att" / "uc04-model-methods.md").read_text(encoding="utf-8")
    assert len(written) == 2 and csv_text.startswith(
        "run,provider,model,tier,prompt_version,method,"
    )
    for name in MODEL_ARMS:
        assert f"`{name}`" in md_text and f",{name}," in csv_text
    # the same method in two folders: the newer folder stands for it, never both
    assignment = attachment.assign_methods([run_dir, run_dir])
    assert set(assignment) == set(MODEL_ARMS) and set(assignment.values()) == {run_dir}
    folders, rows, _ = attachment.model_methods_rows(assignment)
    assert len(folders) == 1 and {r["method"] for r in rows} == set(MODEL_ARMS)


def test_limit_cuts_every_subset_and_reuse_takes_calls_over(
    toy_db: Path, toy_sample: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name, base = toy_sample
    kwargs = dict(
        methods="rank_candidates,rerank_als_top200",
        sample_name=name,
        langs=["en"],
        provider="mock",
        n_neg=3,
        db_path=toy_db,
        base_dir=tmp_path / "runs",
        samples_dir=base,
        attachments_dir=tmp_path / "attachments",
    )
    first = model_arena.run(limit=2, **kwargs)
    config = json.loads((first / "config.json").read_text(encoding="utf-8"))
    assert config["sample"]["customers"] == config["sample"]["customers"][:2]
    top = json.loads((first / "scores" / "rerank_als_top200-en.json").read_text(encoding="utf-8"))
    assert len(top["customers"]) <= 2

    async def no_call(*args, **kwargs):  # pragma: no cover - would fail the test
        raise AssertionError("a reused call must not reach the provider")

    monkeypatch.setattr(_calls, "generate_json", no_call)
    second = model_arena.run(limit=2, reuse=first, **kwargs)
    scores = json.loads((second / "scores" / "rank_candidates-en.json").read_text(encoding="utf-8"))
    assert scores["calls"]["reused"] == scores["calls"]["ok"] == 2
    call = json.loads(
        next((second / "calls" / "rank_candidates-en-mock").glob("*.json")).read_text()
    )
    assert call["reused_from"] == first.name


def test_registry_and_the_single_methods_table(tmp_path: Path) -> None:
    assert resolve("all") == list(MODEL_ARMS)
    assert resolve("rerank_als,rank_candidates") == ["rerank_als", "rank_candidates"]
    with pytest.raises(ValueError):
        resolve("llm_random_pool")
    for module in MODEL_ARMS.values():
        assert module.SUBSET in {"sample", "reachable"}
        assert set(module.PROTOCOLS) <= {"full", "sampled"}
    path = attachment.write_arms_table(tmp_path)
    text = path.read_text(encoding="utf-8")
    for name in list(ARMS) + list(MODEL_ARMS):
        assert text.count(f"| `{name}` |") == 1


def test_profile_lines_follow_the_branch() -> None:
    profile = {
        "ocean": {"O": 4.1, "C": 3.9, "E": 3.2, "A": 3.6, "N": 2.4},
        "lifecycle": "loyal, buying regularly",
        "topics": ["computers / myš"],
        "aspects": [("zvuk", "positive"), ("baterie", "negative")],
    }
    en = rerank_als_with_profile.profile_lines(profile, "en")
    cs = rerank_als_with_profile.profile_lines(profile, "cs")
    assert (
        en[0].startswith("- Big Five (1-5): O 4.1, C 3.9")
        and "praised: zvuk; criticised: baterie" in en[-1]
    )
    assert (
        cs[0].startswith("- Big Five (1–5): O 4,1; C 3,9")
        and "chválí: zvuk; kritizuje: baterie" in cs[-1]
    )
    assert rerank_als_with_profile.profile_lines({}, "en") == []


def test_card_needs_an_arena_run_and_reads_the_records(tmp_path: Path) -> None:
    empty = tmp_path / "runs"
    empty.mkdir()
    assert card.records(empty) == {
        "arena": None,
        "facts": None,
        "personality": None,
        "outputs": None,
        "model": {},
        "comparisons": [],
    }
    with pytest.raises(FileNotFoundError):
        card.build(out_path=tmp_path / "RESULTS.md", runs_dir=empty)
    if attachment.newest_full_run() is None:
        pytest.skip("no committed arena run of record in this checkout")
    path = card.build(out_path=tmp_path / "RESULTS.md")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# UC-04 results") and "runs/" in text
    for name in attachment.record_model_runs():
        assert name in text
