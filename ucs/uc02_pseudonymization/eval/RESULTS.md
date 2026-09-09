# UC-02 results — reversible pseudonymisation of Czech CRM text

Ran on: `uc02-corpus-v2-model`, 100 Czech CRM messages built from the CRM rows (names,
e-mails, phones, addresses, birth dates, bank accounts, IBANs, employers, IČO, DIČ, rodná
čísla), 345 planted personal-data items, prose written by Codex gpt-5.5 (low) around the
exact strings, all 100 messages verified mechanically (`snapshots/corpus-manifest.json`).
Ran: 2026-09-05, the casing table 2026-09-07. Every number below sits in a run
folder under `eval/runs/` with its `config.json` (corpus hashes, package versions,
model revisions) and its own card.

## 1. Detection — `runs/2026-09-05-detection-table-model-corpus-23-configs/`

    found 345 of 345 planted items          (share of the personal data that got masked: 100 %)
    0 false alarms                          (nothing masked that was not personal data)
    strict F1 1.000, partial 1.000          (exact span and type; partial credits a half-found address)
    100 of 100 messages restored exactly    (masking is reversible)
    rules alone: 149 of 345, F1 0.560       (every format identifier, no name, address, organisation or date)
    best NER alone: F1 0.725                (bardsai without the rules; the hybrid is a necessity)

Production configuration: the rule layer (checksummed Czech identifiers) + bardsai
eu-pii-anonimization-multilang (Apache 2.0). Eleven NER backends compared, licences included:
`NER-COMPARISON.md` (bardsai 1.000, bardsai v2 0.984, stulcrad 0.974, Wismut 0.974, bardsai
mini 0.968, Wismut small 0.950, GLiNER 2.5 0.869, GLiNER 0.792, snerta 0.774, richielo 0.734,
Presidio 0.382).

## 2. The sandwich with a real model — `runs/2026-09-05-sandwich-live-codex-plain-tokens-20-messages/`, `-live-claude/`, `-live-codex-entity/`

    codex gpt-5.5, plain tokens:    20 of 20 kept the id and every token on the first attempt; 68 of 68 values restored
    claude sonnet, plain tokens:    20 of 20 first attempt; 68 of 68 values restored
    codex gpt-5.5, entity tokens:   18 of 20 first attempt, 20 of 20 after one reminder each; 14 of 14 suffixed tokens echoed; 68 of 68 restored

Task: summarise the message in three sentences. The two retries: one summary left out the
rodné číslo token; one named a person once although the note named her twice, which the
strict contract does not accept.

## 3. Unification (decision D-UC02-4)

    entity tokens on the record:    64 of 65 inflected name pairs recognised as one person (345 spans → 281 entities)
    restore under every policy:     100 of 100 exact

Default of the envelope: entity tokens (same person = same number, a letter per grammatical
form) with the strict check (every token comes back). Reason (author): the model may need to
know which mentions are one person; on restore the original wording returns. Paths that only
file a note keep plain tokens.

## 4. Review-text detection rates — `runs/2026-09-05-false-alarms-rules-english-reviews-all/`, `…-rules-bardsai-wismut-czech-reviews-all/`

    rules, 45 909 English review texts:   34 detections per 1 000 texts (postal-code and account shapes, IP addresses read as phones)
    rules, 42 744 Czech review texts:     23 per 1 000; 1.6 % of texts touched
    rules + bardsai, same texts:          3 039 per 1 000; 73.3 % of texts touched (PERSON 1 651, ORG 1 318 per 1 000)
    rules + wismut, same texts:           2 092 per 1 000; 52.6 % of texts touched (ORG 1 719, DATE 159 per 1 000)

The detector flagged 1.6% of Czech reviews using rules alone and 73.3% using rules
with bardsai NER. This check treated all reviews as negative examples, without
manual personal-data annotation. A subsequent inspection found reviewer-provided
personal information in some texts, including an email address. These percentages
therefore measure reviews containing detections, not verified false-positive rates.
Product and brand names account for many unwanted detections, but not every detected
span is a false alarm. The separate annotated-corpus F1 results are unaffected.
The `false_alarms` names and labels in the saved run artifacts reflect the original
assumption; this qualification applies to those results as well.

## 4. Casing — `runs/2026-09-07-casing-table-model-corpus-11-configs-rules-casefold/`

    corpus as written:        rules + bardsai F1 1.000        (the table of block 1)
    corpus in lower case:     rules + bardsai F1 0.914        (names 104/131, addresses 28/38; identifiers, firms and dates unchanged)
    corpus in upper case:     rules + bardsai F1 0.882        (names 98/131, dates 6/8)
    next best in lower case:  bardsai v2 0.896, GLiNER 2.5 0.869, wismut 0.855, stulcrad 0.827
    lemmatised before NER:    rules + bardsai 0.939 as written, 0.859 lower   (`runs/2026-09-07-lemma-table-model-corpus-5-configs/`: simplemma lemma per word, names untouched; it hurts, the foreign context costs more than its truecasing gains)
    before the rule fix:      rules + bardsai 0.894 in lower case     (`runs/2026-09-07-casing-table-model-corpus-11-configs/`: the DIČ and IBAN patterns expected the uppercase country prefix, 12 items lost)

Typed input is not always cased like a CRM note: "o petru bartošovi" is missed by bardsai
and found by bardsai v2 and stulcrad, yet on the 131 lower-case names of the corpus v2 finds
106 to bardsai's 104 with worse addresses, and stulcrad 68. The default stays bardsai; the
demo page offers the other backends with both columns. The rule layer reads the country
prefix of DIČ and IBAN in any case since 2026-09-07; the record rows of block 1 re-score
identically with the fix (the corpus is written in upper case). Old GLiNER failed to load
in both casing runs; the eleven other configurations ran. Full table: `CASING-COMPARISON.md`.

## 5. What these numbers do not cover

The corpus is model-written prose around planted values; real notes may be messier. The
review-text detection rates of the NER are measured separately in the overnight run
(section 4 above); the unannotated reviews do not establish a true false-positive rate.
Resistance to re-identification through public registries is a threat model, not a
measurement (chapter 9.3). The 2026-05-31 table (`fusion_refresh/`, F1 0.854) is kept as
evidence of the earlier merge rules and of two evaluation defects found on 2026-09-05.

Rules + bardsai masked every planted item of the 100 messages with no false alarm, the
sandwich brought every value back through two providers, and the model was told which
mentions belong to one person.
