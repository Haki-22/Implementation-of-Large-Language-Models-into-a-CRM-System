# Synthetic Czech dictation — saved inputs and results

This folder contains 20 Czech clips made with Microsoft Edge text-to-speech
(TTS), their reference transcripts and two local Whisper evaluations. It tests
speech transcription and downstream categorisation on synthetic speech, not
real microphone conditions or the security of the MCP conversation.

## Files

| Path | Contents |
| --- | --- |
| `audio/001.wav`–`020.wav` | The recorded 16 kHz mono, 16-bit PCM clips |
| `manifest.jsonl` | Text, voice, planted personal values and expected category per clip |
| `results_whisper-medium_edge-tts.jsonl` | Per-clip outputs for Whisper medium |
| `summary_whisper-medium_edge-tts.json` | Aggregate results and run metadata |
| `results_whisper-large-v3-turbo_edge-tts.jsonl` | Per-clip outputs for the larger Whisper model |
| `summary_whisper-large-v3-turbo_edge-tts.json` | Its aggregate results and metadata |

There are 15 ordinary clips and five challenge scenarios: coreference, an
instruction-injection attempt, a foreign name, an inflected name and a phone
number spelled as words. These few cases illustrate behaviours; they do not
establish general robustness.

## Read a result

Open the matching summary and per-clip JSONL together. A result row contains the
reference transcript, the recognised `hypothesis`, word error rate (`wer`),
planted-value survival counts, predicted category, correctness and latency.
The summary groups these by voice and ordinary/challenge segment and records
the STT model, TTS engine and categoriser mode in `meta`.

The field `pii_recall_overall` measures whether planted values survived in the
transcript. It is not UC-02 detector recall and does not demonstrate masking.
The evaluator categorises the transcript directly; it does not run the complete
chat envelope. Compare categoriser modes before comparing run summaries.

For a thesis claim, cite the exact summary filename and inspect the contributing
rows. The medium run matches the chat's default model; the larger model is a
comparator. Neither turns synthetic-speech results into a real-user benchmark.

## Repeat transcription

Use a disposable copy of the repository if the supplied evidence must remain
unchanged. Run from its root after the [main setup](../../../../README.md#quickstart):

```bash
THESIS_LLM_CALLS=FALSE python -m ucs.uc03_mcp_privacy.eval.run_synth_eval --model medium
THESIS_LLM_CALLS=FALSE python -m ucs.uc03_mcp_privacy.eval.run_synth_eval --model large-v3-turbo
```

These commands reuse the saved audio and manifest, but **overwrite the matching
results and summary files**. They do not create dated run folders. The explicit
switch keeps categorisation local; missing Whisper weights can still download.
Keep both new output files with the exact input manifest/audio and environment
metadata. Different software or hardware may change transcription or timings.

## Generate new audio

Audio generation is a separate experiment, not a prerequisite for reading or
retranscribing the saved clips. It uses the network TTS service and requires
`ffmpeg` for conversion:

```bash
# Only in a disposable copy: replaces audio/ and manifest.jsonl.
python -m ucs.uc03_mcp_privacy.eval.generate_synth_audio
```

The generator deletes and recreates `audio/` and rewrites the manifest. It has no
safe `--help` mode or output-directory option. Do not invoke it just to inspect
installation. Identical text and voice do not guarantee byte-identical output
from a changing hosted TTS service. Preserve the old audio, manifest and both
result pairs together if you create a new dataset.

See the [evaluation overview](../README.md) for metric definitions and limits,
and the [UC-03 guide](../../README.md) for the actual MCP and masking workflow.
