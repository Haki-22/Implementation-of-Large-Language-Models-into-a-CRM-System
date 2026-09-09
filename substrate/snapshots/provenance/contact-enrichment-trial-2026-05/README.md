# Contact-enrichment provider trial (May 2026) — not adopted

Frozen evidence of a design that was tried and dropped. Nothing in the chain reads
these files.

## What was tried

In May 2026 the contact generator had an LLM branch that was to write, for every
contact, a short Czech CRM interaction history (`prior_interactions`, 1–3 telegraphic
notes such as "E-mailem řešil dotaz na zboží; doplněny parametry, uzavřeno.") and, for
about 15 % of contacts, 1–3 typical words of that person for style mirroring
(`frequent_words`). The prompt received the contact's gender, formality, job title and
OCEAN profile; a deterministic template pool served as the offline fallback.

Before a full run, the branch was trialled on the same three clean Czech-origin
contacts with three providers (2026-05-23, `enrich_one_with_lsm` forced so every row
carries `frequent_words`):

| file | provider | model | rows |
| --- | --- | --- | --- |
| `uc01-contact-enrichment-codex-3.json` | codex | gpt-5.4-mini | 3 |
| `uc01-contact-enrichment-claude-haiku-3.json` | claude | haiku | 3 |
| `uc01-contact-enrichment-gemini-3.json` | gemini | gemini-2.5-flash | 3 |

The trial verdict at the time (UC-01 runbook, May 2026) selected Claude Haiku for the
full run because its words shifted visibly with the persona signal (`rád` / `ráda`).

## Why the substrate does not use it

The full run was never made. The Amazon layer (translated reviews joined to every
contact) took over the role of both fields with real behaviour instead of invented
text: the assembler fills `prior_interactions` with the contact's review headlines and
`frequent_words` with the contact's most frequent Czech words. The generator branch,
its two prompts, the template fallback and the provider-trial CLI were removed on
2026-09-02; these nine rows are the only output the
branch ever produced. Each row carries `enrichment_provider`, `enrichment_model` and
`enrichment_status` as written by that code.

Checksums: `_md5sums.txt`. For the current review-derived fields, see the
[substrate guide](../../../README.md).
