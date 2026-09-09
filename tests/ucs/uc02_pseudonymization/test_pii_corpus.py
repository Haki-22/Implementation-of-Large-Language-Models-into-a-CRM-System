"""The planted-PII corpus generator: plan, mock render, verification, gold (D-UC02-1)."""

from __future__ import annotations

import asyncio
import json
import random

import pytest

from ucs.uc02_pseudonymization.code.pii_corpus import (
    PII_TYPES,
    available_values,
    build_model_prompt,
    format_date,
    format_postal_code,
    generate_corpus,
    locate_gold,
    plan_corpus,
    render_mock,
    verify_text,
    write_snapshots,
)

ROWS = [
    {
        "contact_id": 7,
        "first_name": "Romana",
        "last_name": "Slavíková",
        "gender": "f",
        "email": "romana.slavikova64@post.cz",
        "phone": "+420 733 838 851",
        "full_street": "Pod Kostelem 5",
        "city": "Malé Svatoňovice",
        "postal_code": "54234",
        "date_of_birth": "1969-03-23",
        "bank_account": "437983-86960402/3030",
        "iban": None,
        "company_name": "Domácí Potřeby Plzeň a.s.",
        "ico": "69407819",
        "dic": "CZ69407819",
    },
    {
        "contact_id": 9,
        "first_name": "Ctirad",
        "last_name": "Urban",
        "gender": None,
        "email": "ctirad.urban14@seznam.cz",
        "phone": None,
        "full_street": None,
        "city": None,
        "postal_code": None,
        "date_of_birth": None,
        "bank_account": None,
        "iban": None,
        "company_name": None,
        "ico": None,
        "dic": None,
    },
]


def test_formatting_helpers():
    assert format_postal_code("54234") == "542 34"
    assert format_date("1969-03-23") == "23. 3. 1969"


def test_available_values_follow_the_stored_fields():
    full = available_values(ROWS[0], random.Random(1))
    assert set(full) == set(PII_TYPES) - {"IBAN_CZ"}  # the row stores no IBAN
    assert full["ADDRESS"] == "Pod Kostelem 5, 542 34 Malé Svatoňovice"
    sparse = available_values(ROWS[1], random.Random(1))
    assert set(sparse) == {"PERSON", "EMAIL", "RC"}


def test_plan_is_seeded_and_plants_an_oblique_name_form():
    plans = plan_corpus(ROWS, 12, seed=3)
    assert plans == plan_corpus(ROWS, 12, seed=3)
    assert [p["density_band"] for p in plans[:4]] == ["dense", "moderate", "dense", "sparse"]
    persons = [it for p in plans for it in p["items"] if it["pii_type"] == "PERSON"]
    assert any(it["inflected"] for it in persons if "Slavíkov" in it["surface_form"])
    # a contact without a gender gets the nominative only
    assert not any(it["inflected"] for it in persons if "Urban" in it["surface_form"])
    for plan in plans:
        types = [it["pii_type"] for it in plan["items"] if not it["inflected"]]
        assert len(types) == len(set(types))


def test_mock_render_passes_verification_and_gold_is_exact():
    plan = plan_corpus(ROWS, 10, seed=5)[0]
    text = render_mock(plan, random.Random(0))
    assert verify_text(text, plan) == []
    gold = locate_gold(text, plan)
    assert len(gold) == len(plan["items"])
    for span in gold:
        assert text[span["span_start"] : span["span_end"]] == span["surface_form"]
        assert span["entity_id"] == plan["contact_id"] or span["pii_type"] in ("ORG", "ICO", "DIC")


def test_verification_catches_a_missing_string_and_an_extra_name_form():
    plan = {
        "message_id": "m",
        "contact_id": 7,
        "channel": "note",
        "scenario": "x",
        "density_band": "moderate",
        "near_miss_ico": None,
        "items": [
            {
                "pii_type": "PERSON",
                "surface_form": "Romana Slavíková",
                "form": "nom",
                "inflected": False,
            },
            {
                "pii_type": "EMAIL",
                "surface_form": "romana.slavikova64@post.cz",
                "form": "nom",
                "inflected": False,
            },
        ],
    }
    ok = "Volala Romana Slavíková, odpovíme na romana.slavikova64@post.cz během týdne, jak bylo dohodnuto s ní."
    assert verify_text(ok, plan) == []
    missing = (
        "Volala Romana Slavíková a chce odpověď během týdne, jak bylo dohodnuto s ní telefonicky."
    )
    assert any(issue.startswith("missing EMAIL") for issue in verify_text(missing, plan))
    extra = "Volala Romana Slavíková, odpovíme na romana.slavikova64@post.cz; paní Slavíkové jsme to slíbili."
    assert any("occurs" in issue for issue in verify_text(extra, plan))


def test_model_prompt_names_every_string_verbatim():
    plan = plan_corpus(ROWS, 3, seed=5)[0]
    prompt = build_model_prompt(plan)
    for item in plan["items"]:
        assert f'"{item["surface_form"]}"' in prompt


def test_generate_corpus_mock_end_to_end():
    corpus, gold = asyncio.run(generate_corpus(ROWS, n=20, seed=1, renderer="mock"))
    assert len(corpus) == 20
    assert len(gold) == sum(m["gold_span_count"] for m in corpus)
    assert all(m["verification"]["ok"] for m in corpus)
    by_id = {m["message_id"]: m["text"] for m in corpus}
    for span in gold:
        assert (
            by_id[span["message_id"]][span["span_start"] : span["span_end"]] == span["surface_form"]
        )


def test_write_snapshots_refuses_overwrite_and_writes_a_manifest(tmp_path):
    corpus_path = tmp_path / "uc02-pii-corpus.json"
    gold_path = tmp_path / "uc02-pii-gold.jsonl"
    write_snapshots(
        [{"message_id": "m1", "text": "T"}], [], corpus_path, gold_path, manifest={"corpus_id": "t"}
    )
    with pytest.raises(FileExistsError, match="--force"):
        write_snapshots([], [], corpus_path, gold_path)
    write_snapshots([], [], corpus_path, gold_path, overwrite=True)
    manifests = list(tmp_path.glob("corpus-manifest*.json"))
    assert manifests and json.loads(manifests[0].read_text())["corpus_id"] == "t"
