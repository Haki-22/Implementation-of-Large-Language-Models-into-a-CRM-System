"""Tests for the shared text cleaner / scanner (utils.text_hygiene)."""

from __future__ import annotations

import json
import sqlite3

from utils.text_hygiene import (
    CRITICAL_CLASSES,
    audit_paths,
    clean_json,
    clean_text,
    scan_text,
)


def test_zero_width_and_bidi_are_removed():
    assert clean_text("High Speed \u200b\u200bHDMI") == "High Speed HDMI"
    assert clean_text("a\u202eb\u2066c") == "abc"


def test_c0_c1_pua_and_bom_are_removed():
    assert clean_text("Dell \x1cmedia bar\x1d") == "Dell media bar"
    assert clean_text("xy\ufeffz") == "xyz"
    assert clean_text("cute \uf04a face") == "cute face"


def test_unusual_whitespace_becomes_one_space():
    assert clean_text("a\u00a0b\u2028c\u2029d\x0be\x0cf") == "a b c d e f"
    # U+0085 is a C1 control; ftfy reads it as the cp1252 byte 0x85 = ellipsis (web text origin).
    assert clean_text("wait\u0085 more") == "wait\u2026 more"
    assert clean_text("a_x000D_b") == "a b"
    assert clean_text("a   b\tc") == "a b c"


def test_html_entities_are_unescaped_to_fixpoint():
    assert clean_text("&amp;quot;Fire HD 7&amp;quot;") == '"Fire HD 7"'
    assert clean_text("Plug&amp;View") == "Plug&View"
    assert clean_text("&#65533;") is None


def test_mojibake_is_repaired():
    # "–" (en dash) read as cp1252 -> "\u00e2\u20ac\u201c"; ftfy restores it by decoding.
    assert clean_text("slot \u00e2\u20ac\u201c no adapters") == "slot – no adapters"
    # "±" double-mojibaked with all bytes intact (catalog: "DVD\u00c3\u201a\u00c2\u00b1R"); ftfy restores it.
    assert clean_text("DVD\u00c3\u201a\u00c2\u00b1R") == "DVD±R"
    # "™" as Amazon ships it: entities with the C1 byte already lost at the source
    # (raw meta: "Bluetooth&Atilde;&cent;&Acirc;&Acirc;&cent;"). Undecodable, so the
    # explicit _KNOWN_BROKEN table maps it.
    assert clean_text("Bluetooth&Atilde;&cent;&Acirc;&Acirc;&cent; Stereo") == "Bluetooth™ Stereo"



def test_replacement_char_is_removed():
    assert clean_text("Fuji\ufffd camera") == "Fuji camera"


def test_czech_text_survives_untouched():
    cz = "Toto je ofici\u00e1ln\u011b kompatibiln\u00ed s tisk\u00e1rnami DYMO: \u201eJasn\u00e9, lep\u00edc\u00ed \u0161t\u00edtky\u201c \u2013 ov\u011b\u0159eno."
    assert clean_text(cz) == cz


def test_html_tags_only_stripped_on_request():
    raw = "<p>Great <b>case</b></p><script>alert(1)</script> end"
    assert clean_text(raw) == raw
    assert clean_text(raw, strip_html_tags=True) == "Great case end"


def test_empty_becomes_none():
    assert clean_text("") is None
    assert clean_text("\u200b  ") is None
    assert clean_text(None) is None


def test_clean_json_is_recursive_and_keeps_keys():
    obj = {"a\u200b": ["x\u200by", {"b": "c\u00a0d"}], "n": 3}
    assert clean_json(obj) == {"a\u200b": ["xy", {"b": "c d"}], "n": 3}


def test_scan_text_counts_classes():
    counts = scan_text("a\u200b\u200bb c\u00a0&amp;d \u00e2\u20ac\u201c e<br>f")
    assert counts["ZW"] == 2
    assert counts["NBSP"] == 1
    assert counts["HTMLENT"] == 1
    assert counts["MOJI"] == 1
    assert counts["HTMLTAG"] == 1
    assert "C0" not in counts
    assert CRITICAL_CLASSES == frozenset(
        ["ZW", "BIDI", "C0", "C1", "PUA", "VS", "TAGS", "NONCHAR", "FFFD", "MOJI", "ESCSEQ_X000D"]
    )


def test_audit_paths_walks_json_jsonl_and_sqlite(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"t": "x\u200by"}), encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(json.dumps({"t": "ok"}) + "\n", encoding="utf-8")
    con = sqlite3.connect(tmp_path / "c.db")
    con.execute("create table t (s text)")
    con.execute("insert into t values (?)", ("m\u00a0n",))
    con.commit()
    con.close()
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "d.json").write_text(json.dumps({"t": "\ufffd"}), encoding="utf-8")

    report = audit_paths([tmp_path], exclude=["skip/"])

    assert report[str(tmp_path / "a.json")] == {"ZW": 1}
    assert report[str(tmp_path / "b.jsonl")] == {}
    assert report[str(tmp_path / "c.db")] == {"NBSP": 1}
    assert str(tmp_path / "skip" / "d.json") not in report
