# UC-02 casing — ran on: uc02-corpus-v2-model (100 CRM messages, 345 planted personal-data items) under original, lower, upper

NER: bardsai, richielo, presidio, bardsai_v2, bardsai_mini, wismut, wismut_small, snerta, stulcrad, gliner2
Casings: original, lower, upper
Ran: 2026-09-07 21:35, 5 min 46 s

## rules

    original: strict F1 0.560, found 149 of 345, 38 false alarms    (names: 0 of 131)
    lower: strict F1 0.527, found 137 of 345, 38 false alarms       (names: 0 of 131)
    upper: strict F1 0.560, found 149 of 345, 38 false alarms       (names: 0 of 131)

## rules + bardsai

    original: strict F1 1.000, found 345 of 345, 0 false alarms     (names: 131 of 131)
    lower: strict F1 0.894, found 296 of 345, 21 false alarms       (names: 104 of 131)
    upper: strict F1 0.882, found 295 of 345, 29 false alarms       (names: 98 of 131)

## rules + richielo

    original: strict F1 0.734, found 281 of 345, 140 false alarms   (names: 121 of 131)
    lower: strict F1 0.712, found 269 of 345, 142 false alarms      (names: 121 of 131)
    upper: strict F1 0.734, found 281 of 345, 140 false alarms      (names: 121 of 131)

## rules + presidio

    original: strict F1 0.382, found 217 of 345, 574 false alarms   (names: 68 of 131)
    lower: strict F1 0.320, found 175 of 345, 574 false alarms      (names: 27 of 131)
    upper: strict F1 0.503, found 168 of 345, 155 false alarms      (names: 19 of 131)

## rules + bardsai_v2

    original: strict F1 0.984, found 341 of 345, 7 false alarms     (names: 130 of 131)
    lower: strict F1 0.874, found 295 of 345, 35 false alarms       (names: 106 of 131)
    upper: strict F1 0.853, found 305 of 345, 65 false alarms       (names: 115 of 131)

## rules + bardsai_mini

    original: strict F1 0.968, found 337 of 345, 14 false alarms    (names: 129 of 131)
    lower: strict F1 0.714, found 230 of 345, 69 false alarms       (names: 50 of 131)
    upper: strict F1 0.697, found 243 of 345, 109 false alarms      (names: 58 of 131)

## rules + wismut

    original: strict F1 0.974, found 336 of 345, 9 false alarms     (names: 125 of 131)
    lower: strict F1 0.834, found 266 of 345, 27 false alarms       (names: 69 of 131)
    upper: strict F1 0.754, found 230 of 345, 35 false alarms       (names: 44 of 131)

## rules + wismut_small

    original: strict F1 0.950, found 323 of 345, 12 false alarms    (names: 111 of 131)
    lower: strict F1 0.765, found 238 of 345, 39 false alarms       (names: 49 of 131)
    upper: strict F1 0.690, found 201 of 345, 37 false alarms       (names: 18 of 131)

## rules + snerta

    original: strict F1 0.774, found 294 of 345, 121 false alarms   (names: 130 of 131)
    lower: strict F1 0.728, found 261 of 345, 111 false alarms      (names: 106 of 131)
    upper: strict F1 0.734, found 277 of 345, 133 false alarms      (names: 109 of 131)

## rules + stulcrad

    original: strict F1 0.974, found 340 of 345, 13 false alarms    (names: 131 of 131)
    lower: strict F1 0.804, found 255 of 345, 34 false alarms       (names: 68 of 131)
    upper: strict F1 0.952, found 328 of 345, 16 false alarms       (names: 120 of 131)

## rules + gliner2

    original: strict F1 0.869, found 296 of 345, 40 false alarms    (names: 87 of 131)
    lower: strict F1 0.848, found 284 of 345, 41 false alarms       (names: 87 of 131)
    upper: strict F1 0.869, found 296 of 345, 40 false alarms       (names: 87 of 131)

Rules + bardsai scores F1 1.000 on the corpus as written and 0.894 in lower case.
