# local_translators_50sample: three local GGUF models on 50 items (CPU)

50 review items translated locally with Hunyuan-MT-7B, TranslateGemma-27B and Gemma-4-26B-A4B
(GGUF Q5 quantisation, CPU only) to check whether a local model could replace the paid service.

| file | content |
| --- | --- |
| `sample.jsonl` | the 50 items (`item_id, kind, asin, en, cz`) |
| `<model>_translations.jsonl` | per item: `en`, `cz_local` (local model), `cz_vertex` (Google Cloud Translation v3 output for comparison) |
| `summary.json` | per model: load time, inference time, items per second, errors |

Headline: 0.07, 0.047 and 0.218 items per second respectively; the full corpus of 121 781 items
would take roughly 6.5 to 30 days at those measured rates, excluding loading and other overhead. Not adopted.

## Was it used for the frozen translation?

No. Gemma 4 26B-A4B was the best local option (0.22 items/s on CPU, four times faster than
TranslateGemma 27B in this measured configuration); Hunyuan-MT-7B produced broken output
under its prompt format. These timings depend on the tested CPU and prompt format; they are not a
hardware-independent comparison. Local translation was therefore not adopted.
