"""Run folders, the results card, the table runner and the envelope observer (D-UC02-5)."""

from __future__ import annotations

import asyncio
import json

import pytest

from ucs.uc02_pseudonymization.code import ner as ner_module
from ucs.uc02_pseudonymization.code.envelope import with_envelope
from ucs.uc02_pseudonymization.eval import run_table, runs


def _tiny_corpus(tmp_path):
    """Write a one-message corpus and its matching gold spans (person, email, address) under ``tmp_path``."""
    text = "Volal Jan Novák, e-mail jan.novak@email.cz, adresa Adélčina 72, 459 77 Poběžovice."
    corpus_path = tmp_path / "corpus.json"
    gold_path = tmp_path / "gold.jsonl"
    corpus_path.write_text(
        json.dumps(
            [{"message_id": "m1", "text": text, "channel": "note", "density_band": "dense"}]
        ),
        encoding="utf-8",
    )
    rows = []
    for surface, pii_type in (
        ("Jan Novák", "PERSON"),
        ("jan.novak@email.cz", "EMAIL"),
        ("Adélčina 72, 459 77 Poběžovice", "ADDRESS"),
    ):
        start = text.index(surface)
        rows.append(
            {
                "message_id": "m1",
                "span_start": start,
                "span_end": start + len(surface),
                "pii_type": pii_type,
                "surface_form": surface,
            }
        )
    gold_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return corpus_path, gold_path


def test_new_run_dir_never_overwrites(tmp_path):
    first = runs.new_run_dir("t", tmp_path)
    second = runs.new_run_dir("t", tmp_path)
    assert first.exists() and second.exists() and first != second
    assert second.name.endswith("-2")


def test_card_has_header_blocks_and_closing_sentence(tmp_path):
    path = runs.write_card(
        tmp_path,
        title="UC-02 detection — ran on: x",
        header=[("NER", "bardsai"), ("Ran", "today")],
        blocks=[
            {
                "name": "rules + bardsai",
                "lines": [("found 1 of 2", "share masked"), ("0 false alarms", "")],
            }
        ],
        sentence="Rules + bardsai masked half.",
    )
    card = path.read_text(encoding="utf-8")
    assert card.startswith("# UC-02 detection — ran on: x\n\nNER: bardsai\nRan: today\n")
    assert "## rules + bardsai" in card
    assert "found 1 of 2" in card and "(share masked)" in card
    assert card.rstrip().endswith("Rules + bardsai masked half.")


def test_table_runner_writes_a_run_folder(tmp_path):
    corpus_path, gold_path = _tiny_corpus(tmp_path)
    run_dir = run_table.main(
        [
            "--corpus",
            str(corpus_path),
            "--gold",
            str(gold_path),
            "--configs",
            "gold,rules",
            "--tag",
            "t",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )
    for name in (
        "config.json",
        "summary.json",
        "overall.csv",
        "per_type.csv",
        "unification.csv",
        "RESULTS.md",
    ):
        assert (run_dir / name).exists(), name
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["gold"]["overall"]["f1"] == 1.0
    assert summary["rules"]["by_type"]["EMAIL"]["tp"] == 1
    # the postal code inside the address is a partial hit, not a false alarm
    assert summary["rules"]["partial"]["overall"]["fp"] == 0
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config["corpus"]["gold_spans"] == 3 and config["corpus"]["messages"] == 1
    assert (run_dir / "predictions" / "rules.jsonl").exists()
    table = (run_dir / "TABLE.md").read_text(encoding="utf-8")
    assert table.startswith("# UC-02 NER comparison") and "| rules alone |" in table
    target = tmp_path / "NER-COMPARISON.md"
    assert run_table.publish_table(run_dir, target) == target
    assert target.read_text(encoding="utf-8") == table


def test_envelope_reports_every_attempt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ner_module, "detect_ner", lambda text, **_: [])
    seen: list[dict] = []
    calls: list[str] = []

    async def llm(prompt: str) -> str:
        """Fake model call: drops the id-echo token on the first attempt, echoes it from the second on."""
        calls.append(prompt)
        mid = prompt.rsplit("<id>", 1)[1].split("</id>", 1)[0]
        if len(calls) == 1:
            return f"<id>{mid}</id>\nOdpověď bez tokenu."
        return (
            f"<id>{mid}</id>\nPište na <EMAIL_"
            + prompt.split("<EMAIL_", 1)[1].split(">", 1)[0]
            + ">."
        )

    final = asyncio.run(with_envelope("Pište na jan@x.cz.", llm, on_attempt=seen.append))
    assert final == "Pište na jan@x.cz."
    assert [a["attempt"] for a in seen] == [1, 2]
    assert seen[0]["integrity_ok"] is False and seen[0]["missing"]
    assert seen[1]["integrity_ok"] is True and seen[1]["mid_ok"] is True
