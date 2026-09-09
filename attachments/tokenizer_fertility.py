#!/usr/bin/env python3
"""Tokenizer fertility measurement for Czech vs. English.

    Backs the appendix table on the tokenization tax the Czech language pays.

Measures how many tokens the published OpenAI vocabularies spend on the same
concept in Czech and in English. No API access and no model call is involved:
`tiktoken` ships the vocabularies themselves, so the measurement is offline and
reproducible from this file alone.

Vocabularies
    cl100k_base -- GPT-4 and GPT-3.5-turbo
    o200k_base  -- GPT-4o and its successors

Leading space matters. Byte-level BPE treats " customer" and "customer" as
different inputs, because the space is part of the token. A word quoted in
isolation and the same word inside a running sentence therefore need not cost
the same, and a measurement that reports only one of the two is misleading.
Both are reported here for every form.

Usage:
    python tokenizer_fertility.py            # writes tokenizer-fertility.csv
    python tokenizer_fertility.py --print    # also dumps the table to stdout
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import tiktoken

OUT_CSV = Path(__file__).with_name("tokenizer-fertility.csv")

VOCABS = {
    "cl100k_base": "GPT-4, GPT-3.5-turbo",
    "o200k_base": "GPT-4o",
}

# The noun that dominates CRM communication, in the four case forms a Czech
# outreach message actually uses, against its two English forms.
WORDS: list[tuple[str, str, str]] = [
    ("en", "customer", "nominative sg."),
    ("en", "customers", "nominative pl."),
    ("cs", "zákazník", "nominative sg."),
    ("cs", "zákazníka", "genitive/accusative sg."),
    ("cs", "zákazníkovi", "dative/locative sg."),
    ("cs", "zákazníkům", "dative pl."),
]

# Sentence-level fertility: the same greeting a CRM would send, in both
# languages. Fertility = tokens per whitespace-delimited word.
SENTENCES: list[tuple[str, str]] = [
    ("en", "Dear customer, thank you for your order."),
    ("cs", "Vážený zákazníku, děkujeme Vám za Vaši objednávku."),
]


def measure() -> list[dict[str, object]]:
    """Tokenize every word and sentence in `WORDS` and `SENTENCES` with both vocabularies.

    For each word, records the token count when the word stands alone and
    when it is preceded by a leading space (as it would appear mid-sentence),
    plus a `|`-joined dump of the standalone token pieces. For each sentence,
    records the raw token count and a fertility ratio (tokens per
    whitespace-delimited word).

    Returns:
        One dict per word/sentence entry with keys `kind` (`"word"` or
        `"sentence"`), `lang`, `text`, `form`, and per-vocabulary columns
        `{name}_standalone`, `{name}_in_sentence`, `{name}_split` for every
        vocabulary in `VOCABS`.
    """
    rows: list[dict[str, object]] = []
    encoders = {name: tiktoken.get_encoding(name) for name in VOCABS}

    for lang, word, note in WORDS:
        row: dict[str, object] = {"kind": "word", "lang": lang, "text": word, "form": note}
        for name, enc in encoders.items():
            bare = enc.encode(word)
            spaced = enc.encode(" " + word)
            row[f"{name}_standalone"] = len(bare)
            row[f"{name}_in_sentence"] = len(spaced)
            row[f"{name}_split"] = "|".join(enc.decode([t]) for t in bare)
        rows.append(row)

    for lang, sentence in SENTENCES:
        n_words = len(sentence.split())
        row = {"kind": "sentence", "lang": lang, "text": sentence, "form": f"{n_words} words"}
        for name, enc in encoders.items():
            n_tok = len(enc.encode(sentence))
            row[f"{name}_standalone"] = n_tok
            row[f"{name}_in_sentence"] = n_tok
            row[f"{name}_split"] = f"fertility {n_tok / n_words:.2f}"
        rows.append(row)

    return rows


def main() -> None:
    """Run `measure`, write the results to `tokenizer-fertility.csv`, and optionally print them.

    CLI entry point. Always writes `OUT_CSV` next to this script; with
    `--print` also renders a compact one-line-per-entry table to stdout.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="show")
    args = ap.parse_args()

    rows = measure()
    fields = list(rows[0].keys())
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"OK {OUT_CSV.name} ({len(rows)} rows, tiktoken {tiktoken.__version__})")

    if args.show:
        for r in rows:
            print(
                f"{r['lang']:3s} {str(r['text'])[:52]:54s} "
                f"cl100k {r['cl100k_base_standalone']}/{r['cl100k_base_in_sentence']}  "
                f"o200k {r['o200k_base_standalone']}/{r['o200k_base_in_sentence']}  "
                f"{r['cl100k_base_split']}"
            )


if __name__ == "__main__":
    main()
