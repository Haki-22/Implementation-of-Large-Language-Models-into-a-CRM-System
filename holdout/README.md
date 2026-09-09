# `holdout/` — the UC-01 judge calibration set, frozen

One file, `uc01-holdout.json`: 100 Czech CRM messages, each with the contact it
addresses and a label saying whether the message is correct Czech for that person.
It is the set the UC-01 rules judge is calibrated on.

| `subtype` | count | what is wrong with the message |
| --- | --- | --- |
| `valid` | 60 | nothing; 5 of them carry `is_borderline: true` (first-name-only address, a foreign-origin name in the vocative, an academic title) |
| `invalid_vocative` | 10 | the greeting line is mutated or replaced |
| `invalid_tv` | 10 | the T/V register slips (ty and Vy mixed) |
| `invalid_gender` | 10 | gender morphology does not match the contact |
| `invalid_combined` | 10 | several of the above at once |

Every entry has the same shape:

```json
{
  "message_id": "holdout-043",
  "generated_text": "Vážená paní Nováková, ...",
  "contact_data": {"first_name": "Jana", "last_name": "Nováková", "gender": "f", "formal": true, "name_vocative": "Vážená paní Nováková"},
  "subtype": "valid",
  "is_borderline": false
}
```

## Where it comes from and who reads it

`ucs/uc01_personalization/judge_testset.py` builds the set (its module docstring
describes the stratification) and writes it to
`ucs/uc01_personalization/snapshots/uc01-judge-testset.json`, the copy the code reads:
`tests/ucs/uc01_personalization/test_judge.py` calibrates the rules judge on it and
expects all 60 valid messages accepted and 39 of the 40 labelled invalid messages
rejected, the numbers the UC-01 README quotes. The remaining gender example uses
a sender-side form ("jsem ráda"), which the recipient-agreement rule does not check.

This folder holds a frozen copy of that file, kept outside the use-case tree so
that no generator, run or database rebuild can touch it. Nothing reads this folder
by path; it is evidence, not an input. The two files are identical (checked
2026-09-09); to check again:

```bash
cmp holdout/uc01-holdout.json ucs/uc01_personalization/snapshots/uc01-judge-testset.json && echo identical
```
