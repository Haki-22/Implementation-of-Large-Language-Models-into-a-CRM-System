# `substrate/data/` — the committed inputs

Three kinds of data, three places: **this folder holds the committed inputs** the
substrate is built with; `pipeline/data_acquisition/downloaded/` holds the pinned
downloads (not tracked); `snapshots/` holds the outputs. Everything here carries a
`#` provenance header (source, URL or package, reference date, download date, md5
of the raw file, licence) so a reader can check every row.

| file | rows | what | written by | read by |
| --- | --- | --- | --- | --- |
| `cz_age_sex.csv` | 202 | population of Czechia by sex and single year of age (ČSÚ OBY02B, 1. 1. 2025) | `pipeline/data_acquisition/fetch_csu.py` | `generators/csu_sampler.py`: the joint age × sex draw of every contact |
| `cz_municipalities.csv` | 6 254 | every municipality with population, district, region and postal codes (ČSÚ OBY02A, 1. 1. 2026 + Czech Post) | `pipeline/data_acquisition/fetch_csu.py` | `generators/csu_sampler.py`: the address draw of contacts and companies |
| `cz_stopwords.txt` | 423 | the Czech stop-word list of the stopwords-iso project (MIT), one word per line | vendored 2026-09-03 from `stopwordsiso` 0.7.0 | `pipeline/build_substrate_db.py`: the filter behind `Contact.frequent_words` |

Paths in the table are relative to `substrate/`. See the [acquisition guide](../pipeline/data_acquisition/README.md) for root-relative commands and download behaviour.

The ČSÚ tables are derived, not downloaded: `fetch_csu --force` (or `build_all
--force`) regenerates them byte-identically from the pinned raw files. Licence:
CC BY 4.0, "Zdroj: ČSÚ"; the tables are reductions, not official statistics.
The stop-list is vendored rather than imported at build time so the list a reader
checks is the list the database was built with, independent of package versions.
