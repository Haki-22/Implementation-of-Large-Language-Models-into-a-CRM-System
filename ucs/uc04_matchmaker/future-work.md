# UC-04 — future work

What the arena does not do and would be the next step. Everything listed is **not
implemented**; what the earlier version of this file called future work and now exists
(aspect sentiment, interest topics, the lifecycle stage) lives in `outputs_for_uc01/`;
the May churn, sentiment and persona-segmentation baselines were removed on 2026-09-07
(their outputs had no reader; the chapter names none of them).

1. **A second model on the same personality prompt.** The 2026-09-06 rerun inferred every
   linked customer's Big Five profile with one model (`gemini-3.8-flash`); the only
   cross-check is the May run of a different model on 62 people (mean absolute difference
   0.23 of 5, conscientiousness lower across the board, see
   `attachments/ocean-inference.md`). A full second pass with the same prompt would bound
   the noise of the inferred labels for all 425.
2. **A third language branch (German or Slovak).** The Czech branch measures the Czech
   tax of the text arms against English; a second under-represented language would say
   whether the tax is Czech-specific or a property of every language the encoders saw
   little of. Needs a translated catalogue and reviews, which the substrate does not have.
3. **Model arms on the whole population.** The model arms run on the fixed sample of 100
   (`eval/samples/model-arms-100.json`) because a call per customer and branch is the
   cost; a run on all 425 would tighten the intervals the sample leaves wide.
4. **Personality in a model with interactions beyond LightGBM.** The paired comparison
   (`attachments/uc04-personality-feature.md`) found no measurable gain from a profile
   column; a factorisation machine or a two-tower model would be the next place to look
   before concluding the profile carries no signal for recommendation.
