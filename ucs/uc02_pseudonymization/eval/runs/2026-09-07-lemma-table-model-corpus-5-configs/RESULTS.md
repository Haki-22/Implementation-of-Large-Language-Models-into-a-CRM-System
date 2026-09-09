# UC-02 casing — ran on: uc02-corpus-v2-model (100 CRM messages, 345 planted personal-data items) under original, lemma, lower, lemma_lower

NER: bardsai, bardsai_v2, stulcrad, gliner2
Casings: original, lemma, lower, lemma_lower
Ran: 2026-09-07 23:00, 3 min 11 s

## rules

    original: strict F1 0.560, found 149 of 345, 38 false alarms      (names: 0 of 131)
    lemma: strict F1 0.553, found 147 of 345, 40 false alarms         (names: 0 of 131)
    lower: strict F1 0.560, found 149 of 345, 38 false alarms         (names: 0 of 131)
    lemma_lower: strict F1 0.553, found 147 of 345, 40 false alarms   (names: 0 of 131)

## rules + bardsai

    original: strict F1 1.000, found 345 of 345, 0 false alarms       (names: 131 of 131)
    lemma: strict F1 0.939, found 322 of 345, 19 false alarms         (names: 125 of 131)
    lower: strict F1 0.914, found 308 of 345, 21 false alarms         (names: 104 of 131)
    lemma_lower: strict F1 0.859, found 284 of 345, 32 false alarms   (names: 89 of 131)

## rules + bardsai_v2

    original: strict F1 0.984, found 341 of 345, 7 false alarms       (names: 130 of 131)
    lemma: strict F1 0.942, found 325 of 345, 20 false alarms         (names: 125 of 131)
    lower: strict F1 0.896, found 307 of 345, 33 false alarms         (names: 106 of 131)
    lemma_lower: strict F1 0.862, found 291 of 345, 39 false alarms   (names: 95 of 131)

## rules + stulcrad

    original: strict F1 0.974, found 340 of 345, 13 false alarms      (names: 131 of 131)
    lemma: strict F1 0.932, found 322 of 345, 24 false alarms         (names: 124 of 131)
    lower: strict F1 0.827, found 267 of 345, 34 false alarms         (names: 68 of 131)
    lemma_lower: strict F1 0.799, found 251 of 345, 32 false alarms   (names: 53 of 131)

## rules + gliner2

    original: strict F1 0.869, found 296 of 345, 40 false alarms      (names: 87 of 131)
    lemma: strict F1 0.841, found 293 of 345, 59 false alarms         (names: 89 of 131)
    lower: strict F1 0.869, found 296 of 345, 40 false alarms         (names: 87 of 131)
    lemma_lower: strict F1 0.841, found 293 of 345, 59 false alarms   (names: 89 of 131)

Rules + bardsai scores F1 1.000 on the corpus as written and 0.914 in lower case.
