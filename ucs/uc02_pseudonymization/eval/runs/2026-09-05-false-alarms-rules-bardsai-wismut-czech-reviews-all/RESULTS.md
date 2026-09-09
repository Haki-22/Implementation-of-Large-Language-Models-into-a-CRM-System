# UC-02 false alarms — ran on: uc_reviews (the substrate's review texts, no personal data)

NER: bardsai, wismut
Configurations: rules, rules + bardsai, rules + wismut
Ran: 2026-09-05 19:02, 3 h 17 min

## rules (cs)

    22.97 false alarms per 1 000 texts     (982 in 42744 texts; by type: PSC 13.24, BBAN 4.75, PHONE 4.59, EMAIL 0.28, ICO 0.12)
    1.6 % of texts got at least one        (a text that would be masked although it holds no personal data)
    run time 8 s

## rules + bardsai (cs)

    3039.37 false alarms per 1 000 texts   (129915 in 42744 texts; by type: PERSON 1650.55, ORG 1317.61, ADDRESS 50.07, PSC 11.39, BBAN 4.75, PHONE 4.59, EMAIL 0.28, ICO 0.12, DATE 0.02)
    73.3 % of texts got at least one       (a text that would be masked although it holds no personal data)
    run time 25 min 17 s

## rules + wismut (cs)

    2091.59 false alarms per 1 000 texts   (89403 in 42744 texts; by type: ORG 1718.91, DATE 158.9, PERSON 118.57, ADDRESS 72.59, PSC 12.89, BBAN 4.75, PHONE 4.59, EMAIL 0.28, ICO 0.12)
    52.6 % of texts got at least one       (a text that would be masked although it holds no personal data)
    run time 2 h 52 min

On 42744 cs texts with no personal data, rules + bardsai raised 3039.37 false alarms per 1 000 texts and touched 73.3 % of them.
