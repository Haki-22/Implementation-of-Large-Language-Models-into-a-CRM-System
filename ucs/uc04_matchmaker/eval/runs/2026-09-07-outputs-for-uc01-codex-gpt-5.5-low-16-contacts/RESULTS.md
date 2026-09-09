# UC-04 outputs for UC-01 — 2026-09-07-outputs-for-uc01-codex-gpt-5.5-low-16-contacts

Ran on: `substrate.db` (sha256 829ee0499dae…), 425 linked customers
Who: prose for 16 contacts of pick `reading-16`; topics + lifecycle for all 425
Provider / model / tier: codex / gpt-5.5 / low (CLI codex-cli 0.153.4)
Prompts: version 1.0.1, Czech; reasons cite purchase ids, aspects quote verbatim
When: 2026-09-07, 2 min 36 s, 112 model calls

## Recommendation reasons (ALS top-k + one Czech sentence each)

    80 of 80 sentences                                  (schema-valid, evidence ids inside the history shown, within the word rule)
    80 grounded                                         (every cited purchase exists in the customer's history (checked, not trusted))
    21.0 words median, 25 max                           (the rule says at most 30)
    6.9 s median per call                               (the call itself)

## Persona (two Czech sentences)

    16 of 16                                            (schema-valid; not loaded into the database, kept in the handoff and the appendix)

## Aspects (from the Czech reviews, verbatim quotes)

    16 contacts ok, 0 failed, 0 without Czech reviews   (one call per contact)
    78 of 79 quotes found verbatim                      (whitespace and case aside; a paraphrase counts as not grounded)

## Classical fields

    topics for 425 contacts                             (LDA, 30 topics over the catalogue titles, top 5 per contact; lifecycle from the substrate's rule)

80 of 80 recommendation sentences cite only purchases the customer made and 78 of 79 aspect quotes are verbatim in the reviews; these are the checks the thesis reports, because nobody receives these texts and nothing else about them can be measured here. Whether they help a message is judged in UC-01, where the texts are read.
