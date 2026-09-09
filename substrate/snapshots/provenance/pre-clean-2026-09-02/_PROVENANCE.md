# Provenance: snapshots BEFORE the 2026-09-02 cleaning ("dirty" versions)

This folder records the six substrate snapshots exactly as every run before
2026-09-02 used them, including the one-time translation (2026-05-29) and all
May/June use-case results.

**Since 2026-09-03 only one of the six is kept as bytes:**
`uc01-contacts-english-mapped-snapshot.json.gz` (unpacked on demand by
`substrate.pipeline.packing`), because its OCEAN backfill came from an
unrecorded draw and cannot be regenerated. The other five were removed from the
repository because they exceeded GitHub's file limit. Their checksums remain in
`_md5sums.txt`, but this export does not contain all the historical code needed
to reconstruct those exact files.

The raw dumps are md5-pinned public downloads (`build_all --force` fetches them).
`trace_bad_chars.py` in this folder reproduces the dirty-character counts from
those dumps; it does not reconstruct all five removed snapshots. The queue
exactly as sent to the translator survives as the `en` field of
`../translation/stage1-translate.json` (packed as `.json.gz` in this export).
Do not edit; never regenerate *into* this folder.

## What each file is

| file | role before 2026-09-02 | why it is dirty |
|---|---|---|
| `english-items.sent-to-translator.jsonl` | **the exact queue sent to Google Cloud Translation on 2026-05-29** (121 781 items) | built by decoding HTML entities only; the characters Amazon ships as entities were left in |
| `english-amazon.json` | per-user English snapshot the queue was derived from; input of the contact builder | same reason |
| `amazon-original-en.json` | English reviews as read by UC-01 (OCEAN inference, frequent words) and UC-04 | same characters, plus 3 C0 control characters |
| `amazon-translated-cz.json` | Czech reviews as read by UC-01 / UC-04 / UC-02 pilot | zero-width spaces already removed by the old cleaner; 91 reviews still differ from today's (entities, encoding repairs) |
| `amazon-catalog-en.json` | product catalog as read by UC-04 and the DB | 40 mojibake sequences, 29 U+FFFD, double-escaped entities, 59 descriptions with HTML tags |
| `uc01-contacts-english-mapped-snapshot.json` | contacts as loaded into `substrate.db` | 6 histories carry the characters above; also the only place the `_ocean_source` key ever existed |

Origin: the snapshot set in use immediately before the 2026-09-02 rebuild,
i.e. the files every earlier run read. Checksums (`_md5sums.txt`; the five
removed on 2026-09-03 are checked against these when regenerated):

```
44c042b073fb31f0a3e447afde0fd778  amazon-catalog-en.json
4fe8e8730a245e5c7444e63c5ccf8c45  amazon-original-en.json
18f8fd31e3ec01580f7679510738dacb  amazon-translated-cz.json
f6fd65b1a693270114dc6e26e5547edf  english-amazon.json
bb14ebf127cd39cb2f63956990ca6dbe  uc01-contacts-english-mapped-snapshot.json
1515e291b274673247fa36e34a70f7f6  english-items.sent-to-translator.jsonl
```

## What the audit found in them before the removal (`python -m utils.text_hygiene audit <this folder>`, 2026-09-02)

```
CRITICAL substrate/snapshots/provenance/pre-clean-2026-09-02/amazon-catalog-en.json  {'MOJI': 40, 'FFFD': 29} {'HTMLENT': 232, 'HTMLTAG': 11418, 'CJK': 15}
CRITICAL substrate/snapshots/provenance/pre-clean-2026-09-02/amazon-original-en.json  {'FFFD': 7, 'C0': 3} {'HTMLENT': 277, 'HTMLTAG': 112, 'CYR': 2224, 'CJK': 3}
info     substrate/snapshots/provenance/pre-clean-2026-09-02/amazon-translated-cz.json   {'HTMLENT': 199, 'HTMLTAG': 46, 'CJK': 3}
CRITICAL substrate/snapshots/provenance/pre-clean-2026-09-02/uc01-contacts-english-mapped-snapshot.json  {'MOJI': 4, 'FFFD': 7, 'C0': 3} {'HTMLENT': 277, 'HTMLTAG': 114, 'CYR': 2224, 'CJK': 3}
CRITICAL substrate/snapshots/provenance/pre-clean-2026-09-02/english-amazon.json  {'MOJI': 4, 'PUA': 9, 'ZW': 1, 'FFFD': 7, 'C1': 1, 'C0': 3} {'DBLSP': 269916, 'HTMLENT': 1482, 'NBSP': 94, 'HTMLTAG': 114, 'CYR': 2224, 'LSEP': 9, 'CJK': 3}
CRITICAL substrate/snapshots/provenance/pre-clean-2026-09-02/english-items.sent-to-translator.jsonl  {'MOJI': 4, 'PUA': 9, 'ZW': 1, 'FFFD': 7, 'C1': 1, 'C0': 3} {'DBLSP': 268990, 'HTMLENT': 277, 'NBSP': 19, 'HTMLTAG': 114, 'CYR': 2224, 'LSEP': 9, 'CJK': 3}

files: 6  critical hits: 143
```

Classes: ZW zero-width, C0/C1 control characters, PUA private-use glyphs
(Wingdings), FFFD replacement character, MOJI mojibake, NBSP non-breaking
space; HTMLENT/HTMLTAG/CYR/CJK are informational.

## Where the characters come from

Not from our scripts: the Amazon dumps store them as HTML entities
(`&#65533;`, `&#61514;`, `&nbsp;`, `&Atilde;&cent;`). Decoding the entities,
which every pipeline must do, reveals them. The zero-width spaces on the Czech
side were inserted by the translator. Full three-stage trace from the
compressed dumps: `provenance-trace.md` here, produced by `trace_bad_chars.py`
(run from the project root, about 70 s; `audit-counts-before-rebuild.csv` is the
per-file audit of the whole tree before the rebuild that the trace compares against).

## How the current chain differs

`build_english_snapshot.py` cleans the decoded text (`utils.text_hygiene.clean_text`)
before queueing, `build_clean_snapshots.py` cleans the Czech side and repairs the
catalog, and the audit gate refuses any critical class in the outputs. The
frozen `../translation/stage1-translate.json` is untouched: its `en` field equals
the dirty queue here, its `cz_raw` keeps the translator's zero-width spaces.
