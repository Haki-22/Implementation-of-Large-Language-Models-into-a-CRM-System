"""What UC-04 hands to UC-01: the word outputs a classical recommender cannot produce, plus the classical fields.

For the top levels of UC-01's personalisation ladder the message needs, per contact:
recommended products **with a Czech sentence saying why** (a language model writes it,
grounded in the purchases it cites), a **persona** (two Czech sentences about the
customer's buying behaviour), the **product aspects the customer praises or criticises**
(from the customer's Czech reviews, each with a verbatim quote), and two classical
fields, **interest topics** (LDA over the catalogue titles) and the **lifecycle stage**
(the substrate's rule). The assignment calls these category C: tasks classical methods
do not lose on accuracy but structurally cannot perform.

Who gets what is a rule, not a list (decision of 2026-09-06): the model-written prose
for the linked contacts of UC-01's pick (the people whose messages the reading pass looks
at), the classical fields for every linked contact. The recommendations themselves come
from ALS collaborative filtering over the customer's whole purchase history (nothing
hidden: this is the production view, not the arena's leave-one-out).

Flow: ``run`` (calls the model, one run folder with every prompt and answer, the
grounding checks, the handoff file, a card and the appendix pair) -> ``freeze`` (the run's
handoff becomes ``results/uc04_to_uc01_handoff.json``, the file the database build loads
into ``uc_recommendations``, ``uc_topics`` and ``uc_aspects``) -> ``build_all --force
--from database``. Modules: ``prompts`` (the three Czech prompts, versioned), ``calls``
(one recorded call), ``reasons``, ``persona``, ``aspects``, ``topics``, ``handoff``, ``run``.
"""
