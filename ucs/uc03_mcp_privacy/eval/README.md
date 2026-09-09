# UC-03 evaluation — what exists and what its numbers mean

```
eval/
├── README.md                 this file
├── generate_synth_audio.py   synthesises the 20-clip Czech corpus with Microsoft Edge TTS (cloud service)
├── run_synth_eval.py         transcribes every clip with faster-whisper and scores it
├── metrics.py                wer, cer, pii_recall, leak_rate, latency_stats (pure functions)
└── synth/                    the corpus (audio/, manifest.jsonl) and two Whisper runs (results_*, summary_*)
```

## The corpus

Twenty Czech dictations, two Edge TTS voices (10 + 10), fifteen clean clips
across the six note categories and five trick clips (same-name coreference,
prompt injection in the dictation, a foreign name in Czech context, heavy
declension, a phone number spelled in words), 31 personal-data items whose gold
positions are known by construction. The audio is committed, so the corpus is
reproducible as a file; the synthesis itself calls a cloud service whose voices
are not versioned, so re-running the generator may produce different audio.
The generator replaces `audio/` and `manifest.jsonl`. Existing result files stay,
but then refer to the old inputs; preserve the whole set together. Re-running
transcription overwrites the result/summary pair for the chosen model.

## The two runs

`summary_whisper-medium_edge-tts.json` and `summary_whisper-large-v3-turbo_edge-tts.json`
(2026-05-31). Read them with these definitions:

- **WER** — word error rate after lower-casing and stripping punctuation; digit
  grouping is not normalised, so "605 123 456" against "605123456" counts as
  three errors. Part of the reported rate is formatting, not recognition.
- **`pii_recall`** — whether the gold personal-data string survives in the
  transcript (case-insensitive, digits joined). It measures **survival through
  speech recognition**, not detection: no pseudonymiser runs in this script.
  The name is kept for the file format; do not cite it as detector recall.
- **`cat_accuracy`** — the categoriser's agreement with the expected category on
  the raw hypothesis. The path that produced it (keyword rules or a model) was
  not recorded, so the difference between the two runs (0.60 vs 0.95) cannot be
  attributed to the Whisper size. Treat the two figures as not comparable.
- **latency** — per clip, including the model load on the first clip.

## What is not measured yet

The middleware itself: tool-call accuracy of the model on scripted dictations
against the expected database state, a leak check over everything the model
received (its turn, every tool result), end-to-end latency per call, and the
categoriser with its provider recorded. That evaluation is the next step for
UC-03; until it runs, the README of the package claims no number about it.

## How to use

These are separate experiments, not setup steps. Use a disposable repository copy
and run from its root. The [synth guide](synth/README.md) explains what each command
replaces. Reading the existing JSON results requires no model or network.

```bash
python -m ucs.uc03_mcp_privacy.eval.generate_synth_audio            # cloud TTS, rewrites audio/ + manifest
THESIS_LLM_CALLS=FALSE python -m ucs.uc03_mcp_privacy.eval.run_synth_eval --model medium
python -m ucs.uc03_mcp_privacy.eval.run_synth_eval --model large-v3-turbo
```
