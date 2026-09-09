# UC-02 detection — ran on: uc02-corpus-v2-mock (10 CRM messages, 35 planted personal-data items)

NER: bardsai, bardsai_v2, bardsai_mini, wismut, stulcrad, gliner
Configurations: rules + bardsai, rules + bardsai_v2, rules + bardsai_mini, rules + wismut, rules + stulcrad, rules + gliner
Ran: 2026-09-05 18:51, 1 min 43 s

## rules + bardsai

    found 35 of 35 planted items                                                                                                                                               (share of the personal data that got masked: 100.0 %)
    0 false alarms                                                                                                                                                             (things masked that were not personal data)
    strict F1 1.000, partial 1.000                                                                                                                                             (combined score; partial credits a half-found address)
    10 of 10 messages restored exactly                                                                                                                                         (masking is reversible)
    detection 5 s

## rules + bardsai_v2

    found 32 of 35 planted items                                                                                                                                               (share of the personal data that got masked: 91.4 %)
    6 false alarms                                                                                                                                                             (things masked that were not personal data)
    strict F1 0.877, partial 0.959                                                                                                                                             (combined score; partial credits a half-found address)
    10 of 10 messages restored exactly                                                                                                                                         (masking is reversible)
    detection 1 s

## rules + bardsai_mini

    found 34 of 35 planted items                                                                                                                                               (share of the personal data that got masked: 97.1 %)
    2 false alarms                                                                                                                                                             (things masked that were not personal data)
    strict F1 0.958, partial 0.986                                                                                                                                             (combined score; partial credits a half-found address)
    10 of 10 messages restored exactly                                                                                                                                         (masking is reversible)
    detection 1 s

## rules + wismut

    found 34 of 35 planted items                                                                                                                                               (share of the personal data that got masked: 97.1 %)
    2 false alarms                                                                                                                                                             (things masked that were not personal data)
    strict F1 0.958, partial 0.986                                                                                                                                             (combined score; partial credits a half-found address)
    10 of 10 messages restored exactly                                                                                                                                         (masking is reversible)
    detection 2 s

## rules + stulcrad

    found 35 of 35 planted items                                                                                                                                               (share of the personal data that got masked: 100.0 %)
    0 false alarms                                                                                                                                                             (things masked that were not personal data)
    strict F1 1.000, partial 1.000                                                                                                                                             (combined score; partial credits a half-found address)
    10 of 10 messages restored exactly                                                                                                                                         (masking is reversible)
    detection 53 s

## rules + gliner

    found 31 of 35 planted items                                                                                                                                               (share of the personal data that got masked: 88.6 %)
    9 false alarms                                                                                                                                                             (things masked that were not personal data)
    strict F1 0.827, partial 0.880                                                                                                                                             (combined score; partial credits a half-found address)
    10 of 10 messages restored exactly                                                                                                                                         (masking is reversible)
    detection 6 s

## rules + wismut_small

    failed: NER backend 'wismut_small' failed: Wismut/nym-pii-multilingual-small does not appear to have a file named pytorch_model.bin, model.safetensors, tf_model.h5, mod

## rules + snerta

    failed: NER backend 'snerta' failed: 'list' object has no attribute 'keys'

## rules + gliner2

    failed: NER backend 'gliner2' failed: 'ExtractorConfig' object has no attribute 'max_width'

Rules + bardsai masked 100.0 % of the planted personal data with 0 false alarms (strict F1 100.0 %), and 10 of 10 messages restored exactly.
