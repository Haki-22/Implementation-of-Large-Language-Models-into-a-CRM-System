# Third-party notices

The code in this repository is released under the MIT licence in `LICENSE`. That
licence covers the code written for the thesis. The data, model weights, services
and libraries listed here keep their own terms; nothing in this repository
re-licenses them.

## Data redistributed in this repository

### Amazon product reviews, Electronics 5-core (2014 release)

- Source: the Amazon product data released by Julian McAuley and collaborators,
  <https://snap.stanford.edu/data/web-Amazon.html> and <https://jmcauley.ucsd.edu/data/amazon/>.
- What is here: derived snapshots under `substrate/snapshots/amazon/` and
  `substrate/snapshots/provenance/`: the reviews and products of 425 stratified
  reviewers, the machine translation of their reviews into Czech, and the product
  titles. The raw dumps are not in the repository; `substrate/pipeline/data_acquisition/`
  downloads them and checks their recorded md5 sums.
- Terms: the dataset is published for research. Its authors ask that work using it cite
  - J. McAuley, C. Targett, Q. Shi, A. van den Hengel. *Image-based recommendations on styles and substitutes.* SIGIR 2015.
  - R. He, J. McAuley. *Ups and downs: Modeling the visual evolution of fashion trends with one-class collaborative filtering.* WWW 2016.
- The derived snapshots are provided so that the thesis results can be reproduced.
  They remain subject to the source's terms and are not covered by the MIT licence.

### Czech Statistical Office (ČSÚ) open data

- Data sets OBY02A and OBY02B, reduced to `substrate/data/cz_age_sex.csv` and
  `substrate/data/cz_municipalities.csv` by `substrate/pipeline/data_acquisition/fetch_csu.py`.
- Licence: CC BY 4.0, attribution "Zdroj: ČSÚ"
  (<https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu>).
  The two tables are reductions, not official ČSÚ statistics.

### Czech Post postal codes

- "Seznam PSČ částí obcí a obcí bez částí", a public customer output of Česká pošta
  (<https://www.ceskaposta.cz/cs/ke-stazeni/zakaznicke-vystupy>), joined into
  `cz_municipalities.csv` for the postal codes only.

### stopwords-iso

- `substrate/data/cz_stopwords.txt` is the Czech list of the stopwords-iso project
  (<https://github.com/stopwords-iso/stopwords-iso>), MIT licence. The upstream notice is
  reproduced below for this vendored list.

```text
The MIT License (MIT)

Copyright (c) 2020 Gene Diaz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Code adapted into this repository

- `utils/generation/catalog/` is adapted from the author's own `model-catalog` project
  (MIT); see its README for what changed.

## Models downloaded at run time

None of these weights is in the repository. The code downloads them from Hugging Face
on first use. The licence column reflects the model cards and upstream licence
pages checked on 2026-09-09;
check the card before reusing a model outside this prototype, in particular the
non-commercial ones.

| Model | Used by | Licence as stated on the model card |
| --- | --- | --- |
| `bardsai/eu-pii-anonimization-multilang` | UC-02 default NER detector | Apache 2.0 |
| `bardsai/eu-pii-anonimization-multilang-v2-preview` | UC-02 comparator | Apache 2.0 (rolling preview, pinned revision) |
| `bardsai/eu-pii-multi-mini-preview` | UC-02 smoke only | not stated on the card |
| `richielo/small-e-czech-finetuned-ner-wikiann` | UC-02 comparator | CC BY 4.0 |
| [`knowledgator/gliner-x-large`](https://huggingface.co/knowledgator/gliner-x-large) | UC-02 comparator | Apache 2.0 as stated on this model's card |
| `fastino/gliner2.5-multi-v1` | UC-02 comparator | Apache 2.0 |
| `Wismut/nym-pii-multilingual`, `Wismut/nym-pii-multilingual-small` | UC-02 comparators | MIT |
| `ivlcic/snerta-12l-base` | UC-02 comparator | Apache 2.0 (source-corpus terms apply) |
| `stulcrad/CNEC2_0_Supertypes_xlm-roberta-large` | UC-02 comparator | MIT tag; trained on CNEC 2.0, CC BY-NC-SA |
| [NameTag 3 model and code](https://ufal.mff.cuni.cz/nametag/3#license) (ÚFAL MFF UK, LINDAT) | UC-02 optional comparator, assets not in this export | Code: MPL 2.0; models: CC BY-NC-SA 4.0, with any additional source-data conditions |
| Microsoft Presidio with spaCy `en_core_web_lg` | UC-02 comparator | MIT |
| `Systran/faster-whisper-medium` through `faster-whisper` | UC-03 speech to text | MIT |
| `intfloat/multilingual-e5-base` | UC-04 dense retrieval arm | MIT |
| `distilbert-base-uncased`, `UWB-AIR/Czert-B-base-cased` | UC-04 encoder arm (English, Czech) | Apache 2.0, CC BY-NC-SA 4.0 |
| `Unbabel/wmt22-cometkiwi-da` | optional translation-quality scoring, separate environment | CC BY-NC-SA 4.0 |

## Services that produced frozen artefacts

- The Czech translation under `substrate/snapshots/provenance/translation/` was produced
  once, on 2026-05-29, with Google Cloud Translation v3, and is never re-run.
- The saved model outputs in the run folders under `ucs/*/` were produced through the
  Codex, Claude Code and Antigravity command-line tools. Each run's configuration records
  the provider and model. The optional Google speech backends of UC-03 were used only for
  the local-versus-cloud comparison.

## Front-end libraries loaded from a CDN

`thesis-dm-frontend/index.html` loads React and ReactDOM 18.3.1 (MIT), Babel standalone
7.29.0 (MIT), Lucide 0.460.0 (ISC), marked 12.0.2 (MIT) and DOMPurify 3.1.7 (Apache 2.0 or
MPL 2.0) from unpkg. All six are pinned by version; all except Lucide also have
integrity hashes in `index.html`. They are not redistributed here.

## Python dependencies

The packages pinned in `requirements.txt` are installed from PyPI and keep their own
licences. None of them is vendored into this repository.
