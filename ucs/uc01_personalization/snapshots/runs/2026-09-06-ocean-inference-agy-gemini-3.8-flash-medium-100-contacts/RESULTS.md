# OCEAN inference: 100 profiles from English reviews

Date: 2026-09-06
Provider / model / tier: agy / gemini-3.8-flash / medium
Prompt: version 1.2.0, BFI-2 wording, 15 reviews x 600 chars at most
Targets: sample = model-arms-100; pick = reading-16; previous = ocean_inferred.json (62 profiles); limit = 100; exclude_runs = ['2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-20-contacts']; excluded_count = 20; count = 100
Database: substrate/snapshots/substrate.db sha256 b6d82a0dc5a4
Run folder: 2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-100-contacts

## Calls

    100 of 100 profiles        (one call per contact; ok = a schema-valid profile inside 1-5)
    0 failed                   (provider error or a profile outside the range; the response file keeps the reason)
    0 skipped                  (no reviews to read)
    8 min 4 s                  (wall time at concurrency 4)
    247.0 s median per call    (max 483.74 s)
    9861 chars median prompt   (review text the model saw)

## By group

    A: 47 of 47                (group of the substrate)
    B: 48 of 48                (group of the substrate)
    C: 5 of 5                  (group of the substrate)

## Profiles (mean +- sd over the ok calls)

    O 4.14 +- 0.17             (min 3.3, max 4.45)
    C 4.28 +- 0.2              (min 3.45, max 4.7)
    E 3.33 +- 0.3              (min 2.35, max 4.15)
    A 3.69 +- 0.35             (min 2.2, max 4.25)
    N 2.56 +- 0.43             (min 1.95, max 3.95)

100 of 100 targeted contacts received a Big Five profile estimated by gemini-3.8-flash from at most 15 of their English reviews. The profile is a reading of review text, not a measured personality; it enters the database only after `freeze` and a rebuild, with ocean_source = 'inferred' and this folder as its provenance.
