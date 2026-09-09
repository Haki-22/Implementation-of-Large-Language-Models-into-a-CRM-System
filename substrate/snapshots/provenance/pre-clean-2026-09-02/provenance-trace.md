# Provenance trace: where the bad characters come from — 2026-09-02 17:43

Source: `reviews_Electronics_5.json.gz` + `meta_Electronics.json.gz` (md5 identical to the public SNAP files), streamed;
kept 51503 reviews of the 500 stratified reviewers and 19243 catalog products. Script: `trace_bad_chars.py`.

Three states of the same text: **RAW** = the string exactly as stored in the dump (an HTML entity such as `&#65533;` is 8 ASCII characters);
**UNESCAPED** = after `html.unescape`, i.e. what the original step 0c produced (and what
`intermediate/english-amazon.json` contained until 2026-09-02); **CLEANED** = after `utils.text_hygiene.clean_text`.

## Reviews (summary + reviewText + reviewerName)

| class | RAW (as stored in the dump) | UNESCAPED (old step 0c) | CLEANED (new step 0c) |
|---|--:|--:|--:|
| ZW | 0 | 1 | 0 |
| C0 | 3 | 3 | 0 |
| LSEP | 0 | 9 | 0 |
| PUA | 0 | 9 | 0 |
| FFFD | 0 | 7 | 0 |
| HTMLENT | 20340 | 277 | 277 |
| HTMLTAG | 0 | 112 | 112 |

## Catalog (title + description)

| class | RAW (as stored in the dump) | UNESCAPED (old step 0c) | CLEANED (new step 0c) |
|---|--:|--:|--:|
| C1 | 0 | 3 | 0 |
| NBSP | 0 | 6219 | 0 |
| LSEP | 0 | 17 | 0 |
| SHY | 0 | 5 | 0 |
| PUA | 0 | 18 | 0 |
| FFFD | 0 | 29 | 0 |
| MOJI | 0 | 40 | 0 |
| HTMLENT | 24346 | 232 | 60 |
| ESCSEQ_X000D | 4 | 4 | 0 |
| HTMLTAG | 11209 | 11418 | 2 |

How to read the tables: in RAW the hidden characters are almost absent and HTML entities number in the tens of thousands; decoding the entities reveals
U+FFFD, NBSP, PUA (Wingdings) and mojibake, exactly the counts the pre-rebuild audit found in the
`english-amazon.json` of that time (below). The new step removes them.

## Audit of the snapshots before the rebuild (`audit-counts-before-rebuild.csv`)

- `substrate/snapshots/amazon/500-reviewers-en.json`: {'C0': 3, 'CJK': 3, 'CYR': 2224, 'EMOJI': 780, 'EMPTY': 46, 'ESCSEQ': 2, 'FFFD': 7, 'GREEK': 30, 'HTMLENT': 277, 'LONGTOK': 1466, 'NON_NFC': 3, 'PUNCTRUN': 6297, 'SYMBOL': 1393, 'URL': 238}
- `substrate/snapshots/amazon/amazon-items-en.json`: {'CJK': 15, 'EMOJI': 129, 'ESCSEQ': 16, 'FFFD': 29, 'GREEK': 55, 'HTMLENT': 232, 'LONGTOK': 1129, 'MOJI': 40, 'NON_NFC': 3, 'PUNCTRUN': 179, 'SYMBOL': 60, 'TAB': 388, 'URL': 249}
- `substrate/snapshots/intermediate/english-amazon.json`: {'C0': 3, 'C1': 1, 'CJK': 3, 'CYR': 2224, 'DBLSP': 269916, 'EMOJI': 852, 'EMPTY': 2393, 'ESCSEQ': 2, 'FFFD': 7, 'GREEK': 30, 'HTMLENT': 1482, 'LONGTOK': 1476, 'LSEP': 9, 'MOJI': 4, 'NBSP': 94, 'NON_NFC': 3, 'PUA': 9, 'PUNCTRUN': 6297, 'SYMBOL': 1393, 'URL': 238, 'ZW': 1}

## Literal dump lines (reviews)

- **A6VXZ1EEPRTLV / B00005OQMO / summary** — classes after decoding: {'FFFD': 1}
  - RAW: `Solid entry level performer from Fuji&#65533;`
  - UNESCAPED: `Solid entry level performer from Fuji\ufffd`
  - CLEANED: `Solid entry level performer from Fuji`
- **AT2J7H5TRZM8Z / B000068BRB / reviewText** — classes after decoding: {'FFFD': 5}
  - RAW: `I've tried out many different digital cameras over the last thre`
  - UNESCAPED: `I've tried out many different digital cameras over the last thre`
  - CLEANED: `I've tried out many different digital cameras over the last thre`
- **A3QMJMTLJC34QC / B000068MP2 / summary** — classes after decoding: {'FFFD': 1}
  - RAW: `Smooth as a Baby&#65533;s Bare Bottom!`
  - UNESCAPED: `Smooth as a Baby\ufffds Bare Bottom!`
  - CLEANED: `Smooth as a Babys Bare Bottom!`
- **A1VLVWTLV3LVHR / B0009IPTJU / reviewText** — classes after decoding: {'C0': 3}
  - RAW: `What's the best thing about going into an Apple store? The hordes `
  - UNESCAPED: `What's the best thing about going into an Apple store? The hordes `
  - CLEANED: `What's the best thing about going into an Apple store? The hordes`
- **A2NOW4U7W3F7RI / B0055QYJJM / reviewText** — classes after decoding: {'PUA': 1}
  - RAW: `- Charger is cute &#61514;- Absolutely easy to carry, the USB`
  - UNESCAPED: `- Charger is cute \uf04a- Absolutely easy to carry, the USB cable `
  - CLEANED: `- Charger is cute - Absolutely easy to carry, the USB cable`
- **A1G650TTTHEAL5 / B00AJG3NK4 / reviewText** — classes after decoding: {'PUA': 7}
  - RAW: `External batteries are essential for people on-the-go, and especiall`
  - UNESCAPED: `External batteries are essential for people on-the-go, and especiall`
  - CLEANED: `External batteries are essential for people on-the-go, and especiall`
- **A33HIV8RXRDM88 / B00ATM1MVU / reviewText** — classes after decoding: {'PUA': 1}
  - RAW: `Adding to the comments from other reviewers- 50 X Zoom and 16 MP a`
  - UNESCAPED: `Adding to the comments from other reviewers- 50 X Zoom and 16 MP a`
  - CLEANED: `Adding to the comments from other reviewers- 50 X Zoom and 16 MP a`
- **A3FEGTOLCWXSV4 / B00IZGWTVO / reviewText** — classes after decoding: {'ZW': 1}
  - RAW: `&#8203;I recently had a chance to review the Midland ER300, `
  - UNESCAPED: `\u200bI recently had a chance to review the Midland ER300, a very`
  - CLEANED: `I recently had a chance to review the Midland ER300, a very`

## Literal dump lines (catalog)

- **0594481813 / description** — classes after decoding: {'ESCSEQ_X000D': 2}
  - RAW: `Power up your device with this Barnes &amp; Noble OV/HB-ADP Unive`
  - UNESCAPED: `Power up your device with this Barnes & Noble OV/HB-ADP Universal`
  - CLEANED: `Power up your device with this Barnes & Noble OV/HB-ADP Universal`
- **B000DZGA92 / title** — classes after decoding: {'MOJI': 2}
  - RAW: `Jensen WBT212 Universal Bluetooth&Atilde;&cent;&Acirc;&Acirc;&cent; Stereo Headphones`
  - UNESCAPED: `Jensen WBT212 Universal BluetoothÃ¢ÂÂ¢ Stereo Headphones`
  - CLEANED: `Jensen WBT212 Universal Bluetooth™ Stereo Headphones`
- **B000GLIIFW / description** — classes after decoding: {'MOJI': 1}
  - RAW: `Test batteries for remaining power in seconds! The Delkin Batter`
  - UNESCAPED: `Test batteries for remaining power in seconds! The Delkin Batter`
  - CLEANED: `Test batteries for remaining power in seconds! The Delkin Batter`
- **B000HI4VHI / description** — classes after decoding: {'FFFD': 2}
  - RAW: `From the ManufacturerSanDisk Extreme&#xFFFD; IV Compact Flash&#x`
  - UNESCAPED: `From the ManufacturerSanDisk Extreme\ufffd IV Compact Flash\ufffd 4 GB Mem`
  - CLEANED: `From the ManufacturerSanDisk Extreme IV Compact Flash 4 GB Mem`
- **B000JV9LUK / description** — classes after decoding: {'PUA': 9}
  - RAW: `[if gte mso 9]><xml> <w:WordDocument> <w:View>Normal</w:View> <`
  - UNESCAPED: `[if gte mso 9]><xml> <w:WordDocument> <w:View>Normal</w:View> <`
  - CLEANED: `[if gte mso 9]> Normal <`
- **B000SOFV1Q / description** — classes after decoding: {'MOJI': 11}
  - RAW: `Grooved Center Column &#xE2;&#x80;&#x93; prevents unwanted column r`
  - UNESCAPED: `Grooved Center Column â€“ prevents unwanted column rotation, Non-Ro`
  - CLEANED: `Grooved Center Column – prevents unwanted column rotation, Non-Ro`
- **B000UHE8Y2 / description** — classes after decoding: {'PUA': 2}
  - RAW: `Tune for the way you play.The G9 Laser Mouse is built with advan`
  - UNESCAPED: `Tune for the way you play.The G9 Laser Mouse is built with advan`
  - CLEANED: `Tune for the way you play.The G9 Laser Mouse is built with advan`
- **B00111NUM2 / description** — classes after decoding: {'MOJI': 2}
  - RAW: `Nicely affordable and easily mobile, the HP Compaq Presario F750US`
  - UNESCAPED: `Nicely affordable and easily mobile, the HP Compaq Presario F750US`
  - CLEANED: `Nicely affordable and easily mobile, the HP Compaq Presario F750US`

## Czech side: the zero-width characters were inserted by the translator

| where | zero-width characters |
|---|--:|
| translator input (`en` in stage1-translate.json, 121781 items) | 1 |
| translator output (`cz_raw`) | 11002 (in 4794 items) |
| `cz_raw` after `clean_text` | 0 |

- **rt::ADLVFFE4VBT8::B0002L5R78::1229212800**
  - EN input: `Just in case someone may feel guilty for not paying a lot more for, basically the same thing, let's look at our top of t`
  - CZ output (raw): `aši špičkovou nabídku, Monster HDMI 1000HD Ultra-High Speed \u200b\u200bHDMI kabel (2 metry), a proveďme rychlé srovnání. Tato pol`
  - CZ after cleaning: `aši špičkovou nabídku, Monster HDMI 1000HD Ultra-High Speed HDMI kabel (2 metry), a proveďme rychlé srovnání. Tato pol`
- **rt::ADLVFFE4VBT8::B000FDVK2E::1249516800**
  - EN input: `I am positively impressed by this inexpensive 'all-in-one' card reader.For reasons unknown, my Sony A-100 camera, while `
  - CZ output (raw): `e karty Compact Flash a MicroDrive. Nevím, jestli fungují i \u200b\u200bostatní rozhraní. - Červená LED dioda „zapnutí“ mi ukázala`
  - CZ after cleaning: `e karty Compact Flash a MicroDrive. Nevím, jestli fungují i ostatní rozhraní. - Červená LED dioda „zapnutí“ mi ukázala`
- **rt::ADLVFFE4VBT8::B000HKGK8Y::1264896000**
  - EN input: `I am going to award this antenna 4 stars because it's honestly marketed as a 'basic' indoor antenna. And, basic it is. T`
  - CZ output (raw): ` anténa. A základní to tak i je. Není na ní nic zbytečného, \u200b\u200bnic zbytečného a není na ní žádná klamavá reklama. Takže s`
  - CZ after cleaning: `anténa. A základní to tak i je. Není na ní nic zbytečného, nic zbytečného a není na ní žádná klamavá reklama. Takže s`
- **rt::ADLVFFE4VBT8::B000FZX9I0::1223251200**
  - EN input: `It's a good product and it's what I bought 2 years ago but, since then, the 4GB model andKingston 8GB DataTraveler USB f`
  - CZ output (raw): `del a Kingston 8GB DataTraveler USB flash disk - High Speed \u200b\u200bUSB. Dávalo by větší smysl zvolit 8GB model, protože získá`
  - CZ after cleaning: `del a Kingston 8GB DataTraveler USB flash disk - High Speed USB. Dávalo by větší smysl zvolit 8GB model, protože získá`

Run time: 67 s.
