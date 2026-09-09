# UC-02 — Reversible pseudonymisation of Czech CRM text

A privacy layer between a Czech CRM and an external language model. Personal data
in a text is detected, replaced by opaque typed tokens (`<PERSON_1>`, `<ICO_1>`),
the masked text goes to the model, and the model's answer comes back with the
tokens replaced by the original values. Detected values stay local and are restored for the operator. This is risk
reduction, not a guarantee of complete privacy: missed entities can reach the model.

Detection has two layers with different guarantees. The **rule layer** finds
format-bearing Czech identifiers (e-mail, phone, IČO, DIČ, rodné číslo, IBAN,
domestic bank account, postal code) with shared regexes and rejects every
candidate that fails an applicable checksum (not every identifier has one).
The **named-entity recognition (NER) layer** finds names, organisations,
addresses and dates with a public token-classification model. The two meet in one
merge routine: checksummed rule spans win on overlap, a postal code yields to an
address that contains it, and adjacent NER fragments are joined into one span.

Nothing is trained. The models are used as published; the corpus is the exam
paper the detector is scored on.

## Structure

```
uc02_pseudonymization/
├── README.md                   this map
├── __init__.py                 public API (re-exports)
├── code/
│   ├── pseudonymizer.py        rules, merge, masking policies, restore, scoring
│   ├── ner.py                  NER backends (one default, no silent fallback)
│   ├── ner_presidio.py         Microsoft Presidio with Czech recognisers (baseline)
│   ├── envelope.py             the sandwich: mask → model → id echo + token check → restore
│   ├── prompts_envelope.py     prompt catalog of the sandwich (1.3.0)
│   ├── czech_names.py          inflected forms of Czech names for the corpus
│   └── pii_corpus.py           the corpus generator (CRM rows → planted messages + gold)
├── eval/
│   ├── runs.py                 run folders, config.json, the results card
│   ├── run_table.py            the detection table (every configuration, strict + partial)
│   ├── casing_table.py         the same table on the corpus in lower and upper case
│   ├── false_alarms.py         detection rates on unannotated review texts
│   ├── live_check.py           N messages through the sandwich with a real model
│   ├── nametag3_adapter.py     NameTag 3 (ÚFAL) as a detector, separate virtualenv
│   ├── RESULTS.md              one-page results of UC-02, every number with its run folder
│   ├── NER-COMPARISON.md       the generated comparison of the NER backends
│   ├── CASING-COMPARISON.md    the generated comparison under three casings
│   ├── runs/<date>-<tag>/      one folder per evaluation (saved evidence)
│   └── fusion_refresh/         frozen evidence of the 2026-05-31 table (old merge rules)
├── snapshots/                  the corpus of record, its backup, manifests (see its README)
└── _external/                  optional NameTag 3 model + code (not included)
```

## How to use

Start with the [root setup](../../README.md#quickstart). Commands use the repository root; inventory paths below are relative to this package. The default NER model downloads on first use unless already cached. The low-level example is local; the asynchronous envelope example makes a model call and requires `THESIS_LLM_CALLS=TRUE`. Run it inside an async application or notebook.

```python
from ucs.uc02_pseudonymization import pseudonymize, depseudonymize, with_envelope, compose_system_prompt

# Low level: mask and restore locally. Tokens are numbered in reading order.
text = "Pan Jiří Novák volal z +420 605 123 456."
masked, mapping = pseudonymize(text)
# masked  == "Pan <PERSON_1> volal z <PHONE_1>."
# mapping == [{"token": "<PERSON_1>", "surface_form": "Jiří Novák", "source": "ner:bardsai", ...}, ...]
restored = depseudonymize(masked, mapping)

# The sandwich: mask, call the model, check the envelope contract, restore.
from utils.generation import generate_text

async def call(prompt: str) -> str:
    return await generate_text(prompt, provider="codex", system_prompt=compose_system_prompt("Shrň zprávu do tří vět."))

final = await with_envelope(text, call)               # entity tokens (default), random numbers, retries
final = await with_envelope(text, call, unify="none")  # plain tokens: a fresh token per mention
```

Policies of `pseudonymize` / `pseudonymize_text`:

- `unify="none"` (baseline) every span gets its own token; `"exact"` the same value
  shares one token; `"entity"` the same person shares one number and each
  grammatical form gets a letter suffix (`<PERSON_1>` "Jan Novák", `<PERSON_1b>`
  "Novákovi"), so every token still restores to exactly the text it replaced.
- `numbering="reading"` (first PERSON in the text is `<PERSON_1>`) or `"random"`
  (the envelope's default: a number leaks no order).
- The envelope defaults to `unify="entity"`: the model is told that
  two mentions are one person, which a task may need; every token must still come back
  (one retry in twenty in the live check when a summary named the person once), and the
  restore puts each form back where it stood. The sync `pseudonymize` used by UC-03's
  note-taking keeps `"none"`: a filed note does not need the link.
- `ner_backend`: one of `ner.NER_BACKENDS`; `None` is `ner.DEFAULT_NER_BACKEND`.
  A backend that cannot load raises; nothing falls back to another model silently.

Every mapping record carries `source` (`rule` or `ner:<backend>`), so a masked text
says what masked it.

What is stable for a caller: the seven names in `__init__.py` (`with_envelope`,
`compose_system_prompt`, `pseudonymize`, `depseudonymize`, `MappingRegistry`, the two
errors) plus `pseudonymize_text` / `restore_text` and `merge_spans`. Everything else
(`entity_key`, `surname_stem`, `unification_summary`, the NER constants, the `eval`
package) serves the evaluation and may change with the next table.

`with_envelope(..., on_empty="raise")` refuses a text in which nothing was detected
instead of sending it as it is; the default passthrough is logged and reported to the
`on_attempt` observer. A detector miss leaks in either mode; the knob only makes the
empty case an explicit decision of the caller.

## The corpus of record

`snapshots/uc02-pii-corpus.json` + `uc02-pii-gold.jsonl` + `corpus-manifest.json`.
100 Czech CRM messages (notes and customer e-mails) whose personal data comes from
the CRM rows of `substrate.db` (`uc_contacts` joined with `uc_companies`): the
contact's name in the nominative and one oblique form, e-mail, phone, address,
birth date, bank account, IBAN, the employer's name, IČO, DIČ; a rodné číslo from
the identifier generator (no contact stores one); an IČO with a wrong check digit
in about 5 % of messages as a negative control. Eleven types, 345 gold spans, 65
inflected name forms. The gold is exact by construction: the generator knows every
string it planted and records offsets, form label, `inflected` flag and the
contact id as `entity_id`.

Two renderers share one seeded plan. The **model renderer** asks a model for
natural prose around the exact strings and verifies each text mechanically (every
string verbatim, no extra name form, no token-shaped substring, sane length; a
failed text is asked for again, then falls back to the mock and is flagged). The
**mock renderer** builds the text from sentence templates without any model and
is the offline backup (`-mock` pair). The record was rendered on 2026-09-05 by Codex
gpt-5.5 (low tier), all 100 messages verified, 99 at the first attempt; the manifest
names the model and the tier.

The following commands rebuild and replace the saved corpus or its mock backup. They are not installation steps; use a separate copy to retain the supplied corpus and its measurements.

```bash
python -m ucs.uc02_pseudonymization.code.pii_corpus --renderer mock --as-backup --force
python -m ucs.uc02_pseudonymization.code.pii_corpus --renderer model --provider codex --force --force-llm
```

## Evaluation

Every evaluation writes its own folder under `eval/runs/<date>-<tag>/` with
`config.json` (corpus hashes, Python/package versions, model revisions, the
arguments), the machine-readable results and `RESULTS.md`, a one-page card meant to
be attached as it is. A new measurement gets a new run folder. Publishing a saved run regenerates its table and the shared comparison document; it does not run inference. The configuration does not record a Git commit, so preserve the code snapshot separately.

| command (from the repository root) | what it measures |
| --- | --- |
| `python -m ucs.uc02_pseudonymization.eval.run_table --tag table` | every configuration (rules, rules + each NER, each NER alone) on the corpus: strict and partial P / R / F1 per type, restore rate, unification per policy, timing; predictions kept per configuration |
| `python -m ucs.uc02_pseudonymization.eval.casing_table --publish` | rules and rules + every NER backend on the corpus as written, in lower case and in upper case: strict F1 per casing, PERSON and ADDRESS in lower case, the drop; the demo page's NER picker reads the lower-case column; `--casings original,lemma,lower,lemma_lower` adds the corpus lemmatised with simplemma before detection (it hurts: 1.000 → 0.939) |
| `python -m ucs.uc02_pseudonymization.eval.false_alarms` | detections per 1 000 texts on `uc_reviews` (42 744 Czech and 45 909 English review texts without manual PII annotations; these are not verified false-positive rates), rules over all texts, NER over all or a sample |
| `python -m ucs.uc02_pseudonymization.eval.live_check --provider codex --n 20 --force-llm` | N messages through `with_envelope` with a real model: id echo and token integrity per attempt, retries, restore |
| `<venv-nametag3>/bin/python -m ucs.uc02_pseudonymization.eval.nametag3_adapter --out <run>/nametag3_predictions.jsonl` | NameTag 3 predictions for the table (`--nametag3-predictions` adds its rows) |

Scoring: **strict** = exact span and type; **partial** = an overlapping span of the
same type counts once (a half-found address), and a postal code found inside a gold
address counts as a partial hit. The **restore rate** is the share of messages that
come back byte-identical after mask → restore; it is a property of the masking
path, separate from detection.

### Run of record

The one-page summary of every result with its run folder is **[`eval/RESULTS.md`](eval/RESULTS.md)**.

`eval/runs/2026-09-05-detection-table-model-corpus-23-configs/` — the model-rendered corpus of record, eleven
NER backends with and without the rule layer. Rules + bardsai (the default
configuration) found all 345 planted items with no false alarm: strict F1 1.000,
every message restored; the entity policy unified 64 of the 65 inflected name pairs.
The full comparison with licences and the four NER types per backend is
**[`eval/NER-COMPARISON.md`](eval/NER-COMPARISON.md)**, a generated file that names its
source run; every run folder holds the same table as `TABLE.md`, and
`run_table --publish-from <run>` republishes it from any run without the models.
The same hybrids on the corpus in lower and upper case are
**[`eval/CASING-COMPARISON.md`](eval/CASING-COMPARISON.md)** (`casing_table --publish`): in
lower case rules + bardsai keeps F1 0.914 and stays the best hybrid; the rule layer reads
the country prefix of DIČ and IBAN in any case since 2026-09-07 (before that fix it lost
those 12 items in lower case, 0.894); the demo page's NER picker shows both columns.
Order on the record (strict F1 with the rules): bardsai 1.000, bardsai v2-preview 0.984,
stulcrad CNEC 2 supertypes 0.974, Wismut nym-pii 0.974, bardsai mini 0.968, Wismut small
0.950, GLiNER 2.5 0.869, GLiNER 0.792, snerta 0.774, richielo 0.734, Presidio 0.382. The
rules alone find every format-bearing identifier and no name, address, organisation or
date (0.560 strict, 0.703 partial). Standalone backends scored lower on this corpus: the best standalone F1 is
0.725 (bardsai).

Earlier runs of the same code on the mock rendering (template text, easier than notes):
`2026-09-05-detection-table-mock-corpus-9-configs/` (rules + bardsai 0.996), `2026-09-05-candidate-smoke-10-messages-mock-corpus/` (ten
messages, the first look at the six candidates), `2026-09-05-detection-table-mock-corpus-23-configs/` (the
candidates on the full mock rendering).

`eval/runs/2026-09-05-sandwich-live-codex-plain-tokens-20-messages/` — the first 20 messages of the record through the
sandwich with Codex gpt-5.5 (low): 20 of 20 echoed the envelope id and kept every token
on the first attempt, 20 of 20 restored, 68 of 68 original values back in the restored
text, 2 min 23 s.

`eval/runs/2026-09-05-false-alarms-rules-english-reviews-all/` — the rules over all 45 909 English review
texts: 34 detections per 1 000 texts, almost all postal-code and account shapes.

**Review-text detection rates.** On all 42 744 Czech review texts
(`eval/runs/2026-09-05-false-alarms-rules-bardsai-wismut-czech-reviews-all/`),
the detector flagged 1.6% of reviews using rules alone and 73.3% using rules with
bardsai NER. This check treated all reviews as negative examples, without manual
personal-data annotation. A subsequent inspection found reviewer-provided personal
information in some texts, including an email address. These percentages therefore
measure reviews containing detections, not verified false-positive rates. Product
and brand names account for many unwanted detections, but not every detected span
is a false alarm. The separate annotated-corpus F1 results are unaffected. The
`false_alarms` names and labels in the saved run artifacts reflect the original
assumption; this qualification applies to those results as well.

The 2026-05-31 table (`eval/fusion_refresh/`) is kept as frozen evidence of the
previous merge rules and an earlier 69-message corpus, not the current 100-message
corpus. Its best hybrid scored 0.854. Different gold data and merge rules prevent a
direct before/after comparison; see its README for the replay limitations.

### The NER default

`ner.DEFAULT_NER_BACKEND` is one constant read by every path. Its value is whatever
wins the table on the corpus of record after a landscape scan of the models
available at the time; today `bardsai/eu-pii-anonimization-multilang`
(Apache 2.0, XLM-RoBERTa, ONNX INT8 on CPU, 48 ms per text). The six candidates of
the scan, GLiNER, richielo and Presidio stay selectable for the table (see
`eval/NER-COMPARISON.md`); NameTag 3 runs through its adapter.

## Tests

```bash
pytest tests/ucs/uc02_pseudonymization -q      # NER tests may load cached models; inspect skip conditions before an offline run
```

`test_sandwich_mock.py` exercises the whole envelope with a fake model: retries on
a dropped or invented token, on a dropped id, the orphan rule, the provider chain,
concurrent envelopes. `test_pii_corpus.py` and `test_czech_names.py` cover the
generator and the declension table without the database.

## External dependencies

| what | licence | note |
| --- | --- | --- |
| `bardsai/eu-pii-anonimization-multilang` | Apache 2.0 | default NER, downloaded on first use |
| `knowledgator/gliner-x-large` | Apache 2.0 | comparator |
| `richielo/small-e-czech-finetuned-ner-wikiann` | CC BY 4.0 | comparator, PER / ORG / LOC only |
| Microsoft Presidio (+ spaCy `en_core_web_lg`) | MIT | industry baseline, English pipeline on Czech text |
| NameTag 3 model + code (ÚFAL MFF UK, LINDAT) | Code: MPL 2.0; models: CC BY-NC-SA 4.0 | optional comparator; requires separate model/code assets and its own environment |

Saved run tables retain their original licence labels. The current GLiNER label
was corrected to Apache 2.0 after checking its model card; see [NOTICE.md](../../NOTICE.md).

The NameTag adapter is included, but the previously referenced `_external/download_models.sh` helper is not part of this export. NameTag is not required by the GUI or the current 23-configuration table. See the [root README](../../README.md#reproducibility) for the setup boundary; do not reuse May predictions with the current corpus.

Package versions are pinned in `requirements.txt`; each run folder records
the versions and the model revisions it ran with.

## Relationship to UC-03

UC-03 imports this package's detection and restoration primitives. Its envelope
masks chat input and tool responses, then restores known token values in tool
arguments and in the displayed answer. The MCP contact handle and a PERSON token
have different roles; neither token's random number encodes a customer identity.
