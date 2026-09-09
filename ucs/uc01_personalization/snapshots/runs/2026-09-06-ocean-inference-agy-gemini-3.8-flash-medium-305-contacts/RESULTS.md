# OCEAN inference: 305 profiles from English reviews

Date: 2026-09-06
Provider / model / tier: agy / gemini-3.8-flash / medium
Prompt: version 1.2.0, BFI-2 wording, 15 reviews x 600 chars at most
Targets: all = True; exclude_runs = ['2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-20-contacts', '2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-100-contacts']; excluded_count = 120; count = 305
Database: substrate/snapshots/substrate.db sha256 b6d82a0dc5a4
Run folder: 2026-09-06-ocean-inference-agy-gemini-3.8-flash-medium-305-contacts

## Calls

    305 of 305 profiles        (one call per contact; ok = a schema-valid profile inside 1-5)
    0 failed                   (provider error or a profile outside the range; the response file keeps the reason)
    0 skipped                  (no reviews to read)
    24 min 40 s                (wall time at concurrency 4)
    743.6 s median per call    (max 1480.02 s)
    9776 chars median prompt   (review text the model saw)

## By group

    A: 233 of 233              (group of the substrate)
    B: 2 of 2                  (group of the substrate)
    C: 70 of 70                (group of the substrate)

## Profiles (mean +- sd over the ok calls)

    O 4.13 +- 0.18             (min 3.1, max 4.6)
    C 4.2 +- 0.24              (min 2.7, max 4.65)
    E 3.34 +- 0.29             (min 2.5, max 4.35)
    A 3.65 +- 0.41             (min 1.85, max 4.25)
    N 2.57 +- 0.44             (min 1.9, max 4.1)

305 of 305 targeted contacts received a Big Five profile estimated by gemini-3.8-flash from at most 15 of their English reviews. The profile is a reading of review text, not a measured personality; it enters the database only after `freeze` and a rebuild, with ocean_source = 'inferred' and this folder as its provenance.
