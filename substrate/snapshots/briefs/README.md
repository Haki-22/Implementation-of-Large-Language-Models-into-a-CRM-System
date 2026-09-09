# Message briefs — 26 Czech outreach templates

`message_briefs.json` is the author-owned input for UC-01. Each brief has a
machine-readable title, a category and a generic Czech `default_template`.
L0 returns that template unchanged; L1 applies local mail-merge rules; higher
levels use a model to personalise it with the available customer data.

## Origin and revision

The author defined the original 25 topics and categories in May 2026. Their
marketing templates were drafted in a separate model conversation; the model
identity was not logged. This is dataset provenance, not a reproducible
inference run. No script regenerates this file.

On 2026-09-07 the author reviewed all templates, retained their marketing tone,
and corrected three texts: `delivery_delay_apology`,
`urgency_last_chance_sale` and `anniversary_purchase`. Brief 26,
`personal_recommendation`, was added with an author-written upsell template.
It does not assume an accessory relation that the recommender cannot establish.

## How it is used

The database builder loads the file into `uc_message_briefs`; ids are positional
(1–26). UC-01 and the GUI read the database, so editing this JSON requires a
rebuild before those changes appear:

```bash
# From the repository root; replaces the local CRM database.
python -m substrate.pipeline.build_all --force --from database
```

The ladder selection in `ucs/uc01_personalization/picker.py` names three briefs:
`seasonal_sale_launch`, `personal_recommendation` and
`review_request_with_reward`. Existing run folders retain their generated
messages and prompts; changing a template does not update those measurements.

See the [UC-01 guide](../../../ucs/uc01_personalization/README.md) for the ladder
and the [snapshot inventory](../README.md) for the other database inputs.
