# UC-04 outputs for UC-01 — 2026-09-07-outputs-for-uc01-claude-claude-sonnet-5-low-2-contacts

Ran on: `substrate.db` (sha256 829ee0499dae…), 425 linked customers
Who: prose for 2 contacts of pick `reading-16` (limit 2); topics + lifecycle for all 425
Provider / model / tier: claude / claude-sonnet-5 / low (CLI 2.1.263 (Claude Code))
Prompts: version 1.0.0, Czech; reasons cite purchase ids, aspects quote verbatim
When: 2026-09-07, 37 s, 10 model calls

## Recommendation reasons (ALS top-k + one Czech sentence each)

    6 of 6 sentences                                   (schema-valid, evidence ids inside the history shown, within the word rule)
    6 grounded                                         (every cited purchase exists in the customer's history (checked, not trusted))
    22.5 words median, 26 max                          (the rule says at most 30)
    13.4 s median per call                             (the call itself)

## Persona (two Czech sentences)

    2 of 2                                             (schema-valid; not loaded into the database, kept in the handoff and the appendix)

## Aspects (from the Czech reviews, verbatim quotes)

    2 contacts ok, 0 failed, 0 without Czech reviews   (one call per contact)
    10 of 10 quotes found verbatim                     (whitespace and case aside; a paraphrase counts as not grounded)

## Classical fields

    topics for 425 contacts                            (LDA, 30 topics over the catalogue titles, top 5 per contact; lifecycle from the substrate's rule)

6 of 6 recommendation sentences cite only purchases the customer made and 10 of 10 aspect quotes are verbatim in the reviews; these are the checks the thesis reports, because nobody receives these texts and nothing else about them can be measured here. Whether they help a message is judged in UC-01, where the texts are read.
