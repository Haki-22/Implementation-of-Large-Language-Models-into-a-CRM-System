# UC-02 detection — ran on: uc02-corpus-v2-mock (100 CRM messages, 345 planted personal-data items)

NER: bardsai, gliner, richielo, presidio
Configurations: rules, rules + bardsai, rules + gliner, rules + richielo, rules + presidio, bardsai, gliner, richielo, presidio
Ran: 2026-09-05 18:29, 1 min 19 s

## rules

    found 149 of 345 planted items         (share of the personal data that got masked: 43.2 %)
    38 false alarms                        (things masked that were not personal data)
    strict F1 0.560, partial 0.703         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 0 s

## rules + bardsai

    found 343 of 345 planted items         (share of the personal data that got masked: 99.4 %)
    1 false alarms                         (things masked that were not personal data)
    strict F1 0.996, partial 0.999         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 6 s

## rules + gliner

    found 307 of 345 planted items         (share of the personal data that got masked: 89.0 %)
    89 false alarms                        (things masked that were not personal data)
    strict F1 0.829, partial 0.869         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 36 s

## rules + richielo

    found 274 of 345 planted items         (share of the personal data that got masked: 79.4 %)
    161 false alarms                       (things masked that were not personal data)
    strict F1 0.703, partial 0.836         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## rules + presidio

    found 186 of 345 planted items         (share of the personal data that got masked: 53.9 %)
    474 false alarms                       (things masked that were not personal data)
    strict F1 0.370, partial 0.573         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## bardsai

    found 194 of 345 planted items         (share of the personal data that got masked: 56.2 %)
    3 false alarms                         (things masked that were not personal data)
    strict F1 0.716, partial 0.720         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

## gliner

    found 158 of 345 planted items         (share of the personal data that got masked: 45.8 %)
    131 false alarms                       (things masked that were not personal data)
    strict F1 0.498, partial 0.546         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 31 s

## richielo

    found 125 of 345 planted items         (share of the personal data that got masked: 36.2 %)
    220 false alarms                       (things masked that were not personal data)
    strict F1 0.362, partial 0.513         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

## presidio

    found 141 of 345 planted items         (share of the personal data that got masked: 40.9 %)
    480 false alarms                       (things masked that were not personal data)
    strict F1 0.292, partial 0.503         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

Rules + bardsai masked 99.4 % of the planted personal data with 1 false alarm (strict F1 99.6 %), and 100 of 100 messages restored exactly.
