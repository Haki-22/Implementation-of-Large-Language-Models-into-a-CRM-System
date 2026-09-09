# upstream_error-translating-catalog: catalog items the translation API rejected

`error_translating_items.jsonl`: 109 product-title items (`pt::<asin>`) whose Czech translation
came back as an error marker from an earlier catalog translation attempt (`item_id, kind, asin,
en, cz`). Kept as evidence of that API failure sample; it is not a complete explanation
of missing titles in the current catalogue.

## Relationship to the current catalogue

The current catalogue is not English-only: 16 067 of 18 213 products have a Czech
title from the frozen translation. These 109 earlier failures are a separate
record, not its current coverage count. See the [bake-off overview](../README.md)
and the substrate translation-coverage files.
