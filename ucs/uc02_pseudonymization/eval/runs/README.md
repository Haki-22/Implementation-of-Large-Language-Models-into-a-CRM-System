# `eval/runs/` — saved evaluation runs

Name = date · what · on what · how much. Each folder holds `config.json` (corpus hashes,
package versions, model revisions, arguments), the results (`summary.json`, CSVs,
`predictions/` or `messages.jsonl`) and `RESULTS.md`, the one-page card; detection tables
also hold `TABLE.md`. New measurements receive new folders. Report publication can regenerate tables
in an existing folder, so keep a separate copy when preserving byte-identical
evidence. Commands run from the repository root; see the [UC-02 guide](../../README.md).

| folder | what it is |
| --- | --- |
| `2026-09-05-detection-table-mock-corpus-9-configs` | first detection table after the merge fix, on the template-rendered corpus, rules + the four original NER backends |
| `2026-09-05-candidate-smoke-10-messages-mock-corpus` | the six candidates of the landscape scan on ten messages, first look |
| `2026-09-05-detection-table-mock-corpus-23-configs` | all eleven backends with and without rules, template-rendered corpus |
| `2026-09-05-detection-table-model-corpus-23-configs` | **the run of record**: all eleven backends on the Codex-rendered corpus (source of `../NER-COMPARISON.md`) |
| `2026-09-05-sandwich-live-codex-plain-tokens-20-messages` | 20 messages through the sandwich, Codex, a fresh token per mention |
| `2026-09-05-sandwich-live-claude-plain-tokens-20-messages` | the same with Claude |
| `2026-09-05-sandwich-live-codex-entity-tokens-20-messages` | the same with Codex and entity tokens (same person = same number) |
| `2026-09-05-false-alarms-rules-english-reviews-all` | the rule layer over all 45 909 English review texts (used as negative-control text, not a guarantee of no incidental personal data) |
| `2026-09-05-false-alarms-rules-bardsai-wismut-czech-reviews-all` | rules, rules + bardsai, rules + Wismut over all 42 744 Czech review texts |
| `2026-09-07-casing-table-model-corpus-11-configs` | casing comparison before the identifier case-fold fix |
| `2026-09-07-casing-table-model-corpus-11-configs-rules-casefold` | casing comparison after the fix; source of the current casing table |
| `2026-09-07-lemma-table-model-corpus-5-configs` | comparison with local lemmatisation before detection |
