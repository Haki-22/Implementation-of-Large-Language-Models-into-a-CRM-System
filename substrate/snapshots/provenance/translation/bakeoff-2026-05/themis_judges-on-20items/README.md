# themis_judges-on-20items: five judges on the same 20 translations

20 review items translated by Google Cloud Translation v3, judged by COMET-Kiwi and four LLM
judges (Gemini 2.5 Pro, Gemini 2.5 Flash, Claude Sonnet 4.6, Claude Haiku 4.5) with one shared
prompt, to see how much judges agree before choosing one for the pipeline.

| file | content |
| --- | --- |
| `judge_verdicts.csv` | per item: `en`, `cz_raw`, `kind`, `comet_score`, `comet_verdict`, and one verdict column per LLM judge |
| `unanimous_invalid_summary.csv` | the 2 items every judge rejected, with fix counts |
| `unanimous_invalid_detail.json` | those 2 items with every judge's proposed fixes |
| `unanimous_invalid_fixes_longform.csv` | the proposed fixes one per row: `item_id, reported_by, replace, with, why` |

Headline: about 40 % INVALID verdicts across judges on the same 20 items; only 2 items were
rejected unanimously.

## Was it used as a corpus gate?

No judge did. The combined translator/judge trials informed a design choice: Gemini 3.1 Pro in one-shot mode as the
gating judge, COMET-Kiwi as an advisory score, Sonnet dropped (structured-output failures on Czech
quotation marks), batched Opus dropped (over-rejection). The judge stage of the pipeline exists
as archived code (stages 3–4), but no full-corpus gate completed because the run exhausted the
project's credit; the shipped Czech text is stage-1 output without judge gating.
