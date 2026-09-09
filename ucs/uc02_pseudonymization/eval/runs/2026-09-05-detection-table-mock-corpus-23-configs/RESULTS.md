# UC-02 detection — ran on: uc02-corpus-v2-mock (100 CRM messages, 345 planted personal-data items)

NER: bardsai, gliner, richielo, presidio, bardsai_v2, bardsai_mini, wismut, wismut_small, snerta, stulcrad, gliner2
Configurations: rules, rules + bardsai, rules + gliner, rules + richielo, rules + presidio, rules + bardsai_v2, rules + bardsai_mini, rules + wismut, rules + wismut_small, rules + snerta, rules + stulcrad, rules + gliner2, bardsai, gliner, richielo, presidio, bardsai_v2, bardsai_mini, wismut, wismut_small, snerta, stulcrad, gliner2
Ran: 2026-09-05 18:56, 2 min 17 s

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
    detection 22 s

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

## rules + bardsai_v2

    found 332 of 345 planted items         (share of the personal data that got masked: 96.2 %)
    22 false alarms                        (things masked that were not personal data)
    strict F1 0.950, partial 0.984         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 4 s

## rules + bardsai_mini

    found 339 of 345 planted items         (share of the personal data that got masked: 98.3 %)
    10 false alarms                        (things masked that were not personal data)
    strict F1 0.977, partial 0.991         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## rules + wismut

    found 338 of 345 planted items         (share of the personal data that got masked: 98.0 %)
    4 false alarms                         (things masked that were not personal data)
    strict F1 0.984, partial 0.993         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 6 s

## rules + wismut_small

    found 318 of 345 planted items         (share of the personal data that got masked: 92.2 %)
    10 false alarms                        (things masked that were not personal data)
    strict F1 0.945, partial 0.972         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 4 s

## rules + snerta

    found 297 of 345 planted items         (share of the personal data that got masked: 86.1 %)
    116 false alarms                       (things masked that were not personal data)
    strict F1 0.784, partial 0.889         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 8 s

## rules + stulcrad

    found 341 of 345 planted items         (share of the personal data that got masked: 98.8 %)
    8 false alarms                         (things masked that were not personal data)
    strict F1 0.983, partial 0.994         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 11 s

## rules + gliner2

    found 307 of 345 planted items         (share of the personal data that got masked: 89.0 %)
    24 false alarms                        (things masked that were not personal data)
    strict F1 0.908, partial 0.908         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 16 s

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
    detection 18 s

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

## bardsai_v2

    found 183 of 345 planted items         (share of the personal data that got masked: 53.0 %)
    26 false alarms                        (things masked that were not personal data)
    strict F1 0.661, partial 0.704         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 3 s

## bardsai_mini

    found 190 of 345 planted items         (share of the personal data that got masked: 55.1 %)
    11 false alarms                        (things masked that were not personal data)
    strict F1 0.696, partial 0.714         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 1 s

## wismut

    found 189 of 345 planted items         (share of the personal data that got masked: 54.8 %)
    5 false alarms                         (things masked that were not personal data)
    strict F1 0.701, partial 0.712         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 5 s

## wismut_small

    found 169 of 345 planted items         (share of the personal data that got masked: 49.0 %)
    16 false alarms                        (things masked that were not personal data)
    strict F1 0.638, partial 0.672         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 2 s

## snerta

    found 148 of 345 planted items         (share of the personal data that got masked: 42.9 %)
    128 false alarms                       (things masked that were not personal data)
    strict F1 0.477, partial 0.605         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 6 s

## stulcrad

    found 192 of 345 planted items         (share of the personal data that got masked: 55.7 %)
    46 false alarms                        (things masked that were not personal data)
    strict F1 0.659, partial 0.672         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 10 s

## gliner2

    found 158 of 345 planted items         (share of the personal data that got masked: 45.8 %)
    70 false alarms                        (things masked that were not personal data)
    strict F1 0.551, partial 0.551         (combined score; partial credits a half-found address)
    100 of 100 messages restored exactly   (masking is reversible)
    detection 7 s

Rules + bardsai masked 99.4 % of the planted personal data with 1 false alarm (strict F1 99.6 %), and 100 of 100 messages restored exactly.
