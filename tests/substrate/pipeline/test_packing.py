"""Compressed transport of the large snapshots (substrate/pipeline/packing.py)."""

from __future__ import annotations

import json

from substrate.pipeline import packing


def test_pack_is_deterministic_and_unpack_is_exact(tmp_path):
    plain = tmp_path / "big.json"
    plain.write_text(
        json.dumps({"a": list(range(2000)), "cz": "příliš žluťoučký kůň"}, ensure_ascii=False),
        encoding="utf-8",
    )
    original = plain.read_bytes()

    first = packing.pack(plain).read_bytes()
    second = packing.pack(plain).read_bytes()
    assert first == second, "same JSON must give the same .gz bytes (git stays clean)"
    assert packing.status((plain,)) == {str(plain): "ok"}

    plain.unlink()
    assert packing.status((plain,)) == {str(plain): "needs-unpack"}
    assert packing.ensure_unpacked((plain,), announce=False) == [plain]
    assert plain.read_bytes() == original
    assert packing.status((plain,)) == {str(plain): "ok"}


def test_status_sees_a_newer_plain_file(tmp_path):
    plain = tmp_path / "big.json"
    plain.write_text("[1]", encoding="utf-8")
    packing.pack(plain)
    plain.write_text("[1, 2]", encoding="utf-8")  # newer than its .gz
    assert packing.status((plain,)) == {str(plain): "needs-pack"}
    assert packing.ensure_packed((plain,), announce=False) == [packing.packed_path(plain)]
    assert packing.status((plain,)) == {str(plain): "ok"}
    assert packing.status((tmp_path / "none.json",)) == {str(tmp_path / "none.json"): "missing"}
