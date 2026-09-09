# Attachments (generated files the thesis appendix quotes)

Every file here is produced by a command from data that is committed or pinned; none is
typed by hand, and the appendix text quotes them instead of numbers. Rebuilding a table from the same saved measurements is different from running
new inference. A new measurement can change the numbers; the saved run folder is
the source of the quoted result.

Run commands from the repository root after the [main setup](../README.md#quickstart).
Producers overwrite their attachment files. Use the UC guides to choose between
a saved-result export and a new measurement; ellipses in the inventory are
workflow descriptions, not complete shell commands.

| file | producer | what it holds |
| --- | --- | --- |
| `tokenizer-fertility.csv` | `python attachments/tokenizer_fertility.py` (offline, `tiktoken` vocabularies) | token counts of Czech and English word forms and sentences behind Příloha A |
| `uc04-arena-results.csv`, `uc04-arena-results.md` | `python -m ucs.uc04_matchmaker run --arms all …` (a full run rewrites them from its own folder) or `attachment --run <folder>` | one row per regime × protocol × arm × branch of the UC-04 arena, every row with its run folder; the markdown carries Czech table captions |
| `ocean-inference.csv`, `ocean-inference.md` | `python -m ucs.uc01_personalization.ocean_inference attachment` (from the run folders the committed OCEAN snapshot names) | one table per OCEAN inference run (model, calls, wall time, prompt size), the BFI-2 trait means per group, and the agreement with the May 2026 record; the markdown carries Czech captions |
| `uc04-personality-feature.csv`, `uc04-personality-feature.md` | `python -m ucs.uc04_matchmaker personality` (rewrites them from its own folder) | the feature arms in three variants (no profile, inferred profile, sampled profile), hits per variant and the paired differences with sign tests; Czech captions |
| `uc04-outputs-for-uc01.csv`, `uc04-outputs-for-uc01.md` | `python -m ucs.uc04_matchmaker for-uc01 run …` over the whole pick (rewrites them from its own folder; a smoke does not) | counts and grounding of the word outputs UC-04 hands to UC-01 (reasons citing real purchases, verbatim aspect quotes, personas, topics) and examples for three contacts; Czech captions |
| `uc04-data-facts.csv`, `uc04-data-facts.md` | `python -m ucs.uc04_matchmaker facts --population` (rewrites them from its own folder) | the data facts behind the arena numbers: sparsity, reachability of the hidden items, ties, history lengths, Czech coverage, the population sanity check |

Additional result exports:

- `uc01-ladder.{csv,md}` and `uc01-faithfulness.{csv,md}`: `python -m ucs.uc01_personalization card`, assembled from saved runs.
- `uc04-model-methods.{csv,md}`: UC-04 attachment generation from one completed record folder per method.
- `uc04-arms.md`: the classical/model method inventory generated from the registries.

See the [UC-01 guide](../ucs/uc01_personalization/README.md) and [UC-04 guide](../ucs/uc04_matchmaker/README.md) for complete commands and record selection.

Rules: a partial UC-04 run (`run --arms als_cf`) does not touch these files; the UC-04
tables are wide and the appendix page that carries them is rendered landscape; the run
folders under `ucs/uc04_matchmaker/eval/runs/` are the provenance, these files are the
readable copy.
