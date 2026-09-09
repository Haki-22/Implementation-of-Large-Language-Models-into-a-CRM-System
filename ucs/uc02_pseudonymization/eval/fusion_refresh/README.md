# UC-02 detection fusion — frozen May 2026 evaluation

This folder preserves the 2026-05-31 comparison of eleven detector configurations:
five rule-plus-NER hybrids, five standalone named-entity recognition backends,
and rules alone. It used 69 Czech messages with 195 gold spans. The best hybrid
scored strict F1 0.854 under that evaluation's data and merge rules.

This is not the current 100-message, 345-span corpus. The current detector also
merges spans differently. Comparing the two headline scores does not isolate a
code improvement from a change of corpus.

## What is retained

| File | Purpose |
| --- | --- |
| `summary.json` | Overall and per-type measurements for all eleven configurations |
| `overall.csv`, `per_type.csv` | Tabular exports of those measurements |
| `nametag3_predictions.jsonl` | Cached NameTag 3 predictions for the old corpus |
| `fusion_refresh_harness.py` | Harness used for the measurement, retained as evidence |
| `run_nametag3_on_corpus.py` | NameTag subprocess adapter used at the time |
| `venv-ml-snapshot.txt` | Main environment package snapshot |
| `venv-nametag3-snapshot.txt` | Separate NameTag environment package snapshot |

## Reading results versus repeating inference

The JSON and CSV files can be inspected directly without installing any NER
model. They are the saved results, not a promise that the old harness runs against
today's package. That harness imports APIs changed since the measurement and
must not be used as a current installation check.

The exact historical corpus and a complete, compatible execution environment
are not supplied here. A faithful inference rerun would require those inputs
and the original model weights and revisions; the package snapshots alone do
not pin downloaded weights. The supplied measurements remain available for
inspection, but this export does not provide a complete rerun of the May experiment.

For the current supported workflow, use the [UC-02 guide](../../README.md) and
`python -m ucs.uc02_pseudonymization.eval.run_table` from the repository root.
That command performs new inference and can download detector models. It is not
a way to regenerate this May table from its saved numbers.

NameTag remains a valid optional comparator. It needs its own environment and
external model/code assets; the previously referenced download helper is not
included in this export. Its May predictions cannot be reused for a different
corpus. NameTag is not required by the GUI or the current 23-configuration table.

## Scoring conventions of this record

Before scoring, the harness renamed rule `IBAN` to gold `IBAN_CZ` and removed
standalone `PSC` (postal-code) detections because this gold taxonomy represents
postal codes inside `ADDRESS`. Twelve rule false positives were labelled `BBAN`
(domestic bank account), which had no matching category in the old gold. These
conventions belong to this record; they are not the current scorer's contract.
