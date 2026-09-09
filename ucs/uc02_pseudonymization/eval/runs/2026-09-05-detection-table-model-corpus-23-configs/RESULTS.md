# UC-02 detection — ran on: uc02-corpus-v2-model (100 CRM messages, 345 planted personal-data items)

NER: bardsai, gliner, richielo, presidio, bardsai_v2, bardsai_mini, wismut, wismut_small, snerta, stulcrad, gliner2
Configurations: rules, rules + bardsai, rules + gliner, rules + richielo, rules + presidio, rules + bardsai_v2, rules + bardsai_mini, rules + wismut, rules + wismut_small, rules + snerta, rules + stulcrad, rules + gliner2, bardsai, gliner, richielo, presidio, bardsai_v2, bardsai_mini, wismut, wismut_small, snerta, stulcrad, gliner2
Ran: 2026-09-05 19:44, 3 min 12 s

## rules

    found 149 of 345 planted items         (share of the personal data that got masked: 43.2 %)
    38 false alarms                        (things masked that were not personal data)
    strict F1 0.560, partial 0.703         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 0 s

## rules + bardsai

    found 345 of 345 planted items         (share of the personal data that got masked: 100.0 %)
    0 false alarms                         (things masked that were not personal data)
    strict F1 1.000, partial 1.000         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 9 s

## rules + gliner

    found 313 of 345 planted items         (share of the personal data that got masked: 90.7 %)
    132 false alarms                       (things masked that were not personal data)
    strict F1 0.792, partial 0.803         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 31 s

## rules + richielo

    found 281 of 345 planted items         (share of the personal data that got masked: 81.4 %)
    140 false alarms                       (things masked that were not personal data)
    strict F1 0.734, partial 0.859         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## rules + presidio

    found 217 of 345 planted items         (share of the personal data that got masked: 62.9 %)
    574 false alarms                       (things masked that were not personal data)
    strict F1 0.382, partial 0.509         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## rules + bardsai_v2

    found 341 of 345 planted items         (share of the personal data that got masked: 98.8 %)
    7 false alarms                         (things masked that were not personal data)
    strict F1 0.984, partial 0.996         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 5 s

## rules + bardsai_mini

    found 337 of 345 planted items         (share of the personal data that got masked: 97.7 %)
    14 false alarms                        (things masked that were not personal data)
    strict F1 0.968, partial 0.989         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## rules + wismut

    found 336 of 345 planted items         (share of the personal data that got masked: 97.4 %)
    9 false alarms                         (things masked that were not personal data)
    strict F1 0.974, partial 0.988         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 9 s

## rules + wismut_small

    found 323 of 345 planted items         (share of the personal data that got masked: 93.6 %)
    12 false alarms                        (things masked that were not personal data)
    strict F1 0.950, partial 0.962         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 8 s

## rules + snerta

    found 294 of 345 planted items         (share of the personal data that got masked: 85.2 %)
    121 false alarms                       (things masked that were not personal data)
    strict F1 0.774, partial 0.887         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 10 s

## rules + stulcrad

    found 340 of 345 planted items         (share of the personal data that got masked: 98.6 %)
    13 false alarms                        (things masked that were not personal data)
    strict F1 0.974, partial 0.989         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 16 s

## rules + gliner2

    found 296 of 345 planted items         (share of the personal data that got masked: 85.8 %)
    40 false alarms                        (things masked that were not personal data)
    strict F1 0.869, partial 0.884         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 16 s

## bardsai

    found 196 of 345 planted items         (share of the personal data that got masked: 56.8 %)
    0 false alarms                         (things masked that were not personal data)
    strict F1 0.725, partial 0.725         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 3 s

## gliner

    found 164 of 345 planted items         (share of the personal data that got masked: 47.5 %)
    171 false alarms                       (things masked that were not personal data)
    strict F1 0.482, partial 0.494         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 26 s

## richielo

    found 132 of 345 planted items         (share of the personal data that got masked: 38.3 %)
    211 false alarms                       (things masked that were not personal data)
    strict F1 0.384, partial 0.523         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

## presidio

    found 168 of 345 planted items         (share of the personal data that got masked: 48.7 %)
    588 false alarms                       (things masked that were not personal data)
    strict F1 0.305, partial 0.452         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

## bardsai_v2

    found 192 of 345 planted items         (share of the personal data that got masked: 55.7 %)
    14 false alarms                        (things masked that were not personal data)
    strict F1 0.697, partial 0.711         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 4 s

## bardsai_mini

    found 188 of 345 planted items         (share of the personal data that got masked: 54.5 %)
    19 false alarms                        (things masked that were not personal data)
    strict F1 0.681, partial 0.707         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

## wismut

    found 187 of 345 planted items         (share of the personal data that got masked: 54.2 %)
    13 false alarms                        (things masked that were not personal data)
    strict F1 0.686, partial 0.705         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 7 s

## wismut_small

    found 174 of 345 planted items         (share of the personal data that got masked: 50.4 %)
    37 false alarms                        (things masked that were not personal data)
    strict F1 0.626, partial 0.640         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 5 s

## snerta

    found 145 of 345 planted items         (share of the personal data that got masked: 42.0 %)
    131 false alarms                       (things masked that were not personal data)
    strict F1 0.467, partial 0.605         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 9 s

## stulcrad

    found 191 of 345 planted items         (share of the personal data that got masked: 55.4 %)
    50 false alarms                        (things masked that were not personal data)
    strict F1 0.652, partial 0.669         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 14 s

## gliner2

    found 147 of 345 planted items         (share of the personal data that got masked: 42.6 %)
    86 false alarms                        (things masked that were not personal data)
    strict F1 0.509, partial 0.526         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 9 s

Rules + bardsai masked 100.0 % of the planted personal data with 0 false alarms (strict F1 100.0 %), and 100 of 100 messages restored exactly.
