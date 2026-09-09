"""Amazon Reviews translation (EN -> CZ) — the two stages still in use.

    1. Google Cloud Translation v3     -> stage1-translate.json  (FROZEN, ran once)
    2. COMET-Kiwi quality report  -> comet_extract_pairs.py + comet_score.py
                                     (portable scorer: CPU here, GPU elsewhere)

Stages 3-5 of the original design (Gemini judge, Sonnet judge, human-in-the-loop (HITL) queue +
assembly) never gated the shipped corpus and are kept as frozen evidence under
``substrate/snapshots/provenance/translation/judge-stages-unused/``. See
``README.md`` here and that directory's README.
"""
