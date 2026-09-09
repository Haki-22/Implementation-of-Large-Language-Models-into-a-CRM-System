# OCEAN inference: 20 profiles from English reviews

Date: 2026-09-06
Provider / model / tier: agy / gemini-3.8-flash / medium
Prompt: version 1.2.0, BFI-2 wording, 15 reviews x 600 chars at most
Targets: sample = model-arms-100; pick = reading-16; previous = ocean_inferred.json (62 profiles); limit = 20; count = 20
Database: substrate/snapshots/substrate.db sha256 b6d82a0dc5a4
Run folder: 2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-20-contacts

## Calls

    20 of 20 profiles          (one call per contact; ok = a schema-valid profile inside 1-5)
    0 failed                   (provider error or a profile outside the range; the response file keeps the reason)
    0 skipped                  (no reviews to read)
    1 min 53 s                 (wall time at concurrency 4)
    62.6 s median per call     (max 113.21 s)
    9760 chars median prompt   (review text the model saw)

## By group

    A: 20 of 20                (group of the substrate)

## Profiles (mean +- sd over the ok calls)

    O 4.12 +- 0.08             (min 3.95, max 4.25)
    C 4.21 +- 0.11             (min 4.05, max 4.45)
    E 3.47 +- 0.17             (min 3.1, max 3.8)
    A 3.8 +- 0.33              (min 2.75, max 4.15)
    N 2.35 +- 0.3              (min 2.05, max 3.35)

20 of 20 targeted contacts received a Big Five profile estimated by gemini-3.8-flash from at most 15 of their English reviews. The profile is a reading of review text, not a measured personality; it enters the database only after `freeze` and a rebuild, with ocean_source = 'inferred' and this folder as its provenance.
