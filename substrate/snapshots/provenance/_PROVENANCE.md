# `substrate/snapshots/provenance/` — frozen evidence

Everything here is an artifact of a run that is never repeated. The files are
kept next to the data as provenance of the runs that produced the results, so
the results stay reproducible and auditable without repeating anything paid or
one-off. No script regenerates them; the audit gate (`utils.text_hygiene audit`)
excludes this folder on purpose because part of it is deliberately dirty.

| folder | what | used by the chain? |
|---|---|---|
| `translation/` | `stage1-translate.json`, the result of the one-time Google Cloud Translation v3 run (121 781 items, 113 687 translated), its README; `frozen-reviewers.json`, the 500 reviewer ids that run covers and therefore the only pool the stratification may select from; `judge-stages-unused/`, stages 3-5 of the original design (not runnable, never used for results); and `bakeoff-2026-05/` with the trials that chose the translator and the judges (each trial folder has a README stating whether it reached production and why). | **yes** — `build_clean_snapshots.py` joins Czech text from it by item id; `fetch_and_filter.py` selects reviewers only from `frozen-reviewers.json`; `build_english_snapshot --check-against-frozen` proves every queued item has a translation here |
| `pre-clean-2026-09-02/` | the six snapshots exactly as used before the 2026-09-02 cleaning, including the queue as sent to the translator. `_PROVENANCE.md` + `_md5sums.txt` inside. | no (evidence that the bad characters were present at run time and where they came from) |
| `contact-enrichment-trial-2026-05/` | the nine rows (3 contacts x 3 providers) produced by the contact generator's LLM branch before it was dropped in favour of the translated reviews; README + `_md5sums.txt` inside. | no |
| `ocean-inference-2026-05-29/` | what Gemini said about the OCEAN profiles: how the 62 inferred cohort profiles were produced vs the 323 sampled ones, and the Gemini-CLI trial output on 50 other reviewers. README inside. | no |

Never write here. If a future run produces new frozen evidence, add a new dated
folder with its own README and checksums.

## The translation in short

- **Chosen:** Google Cloud Translation v3, one pass over 121 781 items on 2026-05-29. It scored
  highest on the 100-item trial (COMET-Kiwi 0.762 vs 0.750 for Claude Opus and 0.742 for Gemini
  3.1 Pro as translators), ran about six times faster per item, was the only option affordable for
  the corpus and produced no formatting artifacts.
- **Not used, and why:** LLM translators (lower score, slower, artifacts); local models (0.05 to
  0.2 items/s on CPU, one broken); the 16 290 translations from earlier sessions (real output of the
  same service, but the run re-translated the whole queue because stage 1 resumes only against its
  own file, and the planned assembly step never ran, so one run became the single source: 13 844
  of them came back byte-identical, 2 446 differ); the judge stages 2-5 (the translation exhausted
  the project's credit, the Gemini judge stopped at 22 % with a billing error).
- **What shipped:** stage-1 output as is, 113 687 items (93.4 %), the rest lost to a
  per-minute quota with no retry; 14 reviewers lost every review. The audit of the service's output
  (0.85 % of pairs flagged by both COMET-Kiwi and the Gemini judge) is the basis for shipping it
  without judge gating. The input at run time was decoded but not cleaned; the cleaning since
  2026-09-02 keeps the same item ids, see `pre-clean-2026-09-02/`.
