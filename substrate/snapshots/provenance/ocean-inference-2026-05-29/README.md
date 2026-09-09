# `ocean-inference-2026-05-29/` — what Gemini said about the OCEAN profiles

OCEAN = the Big Five personality profile (Openness, Conscientiousness, Extraversion,
Agreeableness, Neuroticism), five numbers on the 1-5 BFI scale stored on a contact.

This is a historical record, not the current database state. Since September 2026,
the current snapshot covers all 425 linked reviewers with new inference runs.
These profiles are model estimates from review text, not measured personality.
Paths and counts in the following table describe the May layout.

## Two kinds of profile in the May substrate

| kind | how | contacts | where |
| --- | --- | --- | --- |
| **Sampled** | the contact generator draws each trait from a truncated normal with BFI-2 population norms (Soto & John 2017), seeded; nothing about the person goes in, it is a plausible random profile | 323 of 500 (the generator leaves 30 % without one on purpose, as missing-data realism) | `contacts/uc01-contacts-english-mapped-snapshot.json`, projected in `ocean/ocean_synthetic_500.json` |
| **Inferred** | `ucs/uc01_personalization/code/amazon_ocean_inference.py`: an LLM reads the reviewer's English Amazon reviews and estimates the five traits, quoting one passage per trait as evidence; run on 2026-05-29 with Gemini 3.1 Pro | 62 of the 67 UC-01 cohort contacts (5 calls failed: `ADLVFFE4VBT8`, `A2RU4U1JZ3DMP5`, `A2WPL6Y08K6ZQH`, `AVBLGXSWRN666`, `AENLD33KQ6MJ4`) | `ucs/uc01_personalization/snapshots/ocean_inferred.json` |

Five calls had no usable result. A JSON-parsing problem was suspected at the
time, but the failed-call logs were not retained, so the cause cannot be verified.
The May snapshot remains here alongside the earlier CLI trial. New inference is
documented in the [current UC-01 guide](../../../../ucs/uc01_personalization/README.md).

In the May database the inferred profile overrode the sampled one for those 62 contacts
(`ocean_source = "inferred"`); the other 438 contacts carried the sampled profile or none.
Of the 67 cohort members, 62 are inferred, 4 fell back to a sampled profile and 1
(`A2WPL6Y08K6ZQH`) had neither.

## The files here

`ocean_inferred-2026-05-29.json`: the 62 profiles of the 2026-05-29 run exactly as the
database read them until 2026-09-06 (`ucs/uc01_personalization/snapshots/ocean_inferred.json`
before the rerun). Moved here as the record of the first run when the whole set was
re-inferred with one current provider, prompt version 1.2.0, into run folders under
`ucs/uc01_personalization/snapshots/runs/<date>-ocean-inference-agy-gemini-3.8-flash-medium-*/`
(`ocean_inference infer`, then `freeze`). On the 13 reviewers both runs cover the profiles
differ by 0.23 points of five on average (max 0.65); the rerun rates conscientiousness
lower across the board.


`gemini-cli-ocean-refer.json` (`kind: ocean_inferred_gemini_cli`): the same inference run
earlier through the Gemini command-line client on **50 reviewers that are not in the cohort**
(no overlap with the 62 shipped profiles). Same output shape: five traits plus one evidence
quote per trait. It is the record of the inference trial that preceded the cohort run and shows
what the model produces from raw reviews; nothing reads it.

## History note

On 2026-05-29 the 177 sampled-empty contacts were filled by an unrecorded second draw from the
generator's sampler. That backfill was reverted on 2026-09-02 (no reader in code, seed not
recoverable); the contacts as the May results read them, with the backfill, remain in
`../pre-clean-2026-09-02/uc01-contacts-english-mapped-snapshot.json.gz`.
