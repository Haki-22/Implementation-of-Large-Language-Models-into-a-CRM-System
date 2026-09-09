"""Deterministic Czech CRM notes for the shared evaluation substrate.

A note is the short record a salesperson leaves on a contact ("reklamoval
poškozený obal zásilky, sjednána sleva 10 %"). Eighty of them are seeded into
the substrate, and they earn their place twice over:

- **UC-03** treats ``uc_notes`` as the writable CRM surface. Its MCP tools read
  notes and append new ones, which makes it the only table anything writes at
  run time.
- **UC-02** can use them as short Czech text quoting a contact's own personal
  data. Today UC-02 reads a separate corpus file; decision D-DB-2 makes the
  contact rows the source that corpus is generated from.

Recipe (no LLM, fully seeded):

``_distribution``
    A weighted contact assignment, so a small hot set of contacts collects
    repeated notes and most collect none — a flat spread would look nothing
    like a real CRM.
``_templates``
    The Czech content: two template pools plus the gender-bearing verb table.
    Categories come from :data:`substrate.constants.NOTE_CATEGORIES`, the same
    list UC-03's categoriser enforces, so seeded notes and notes written at run
    time share one vocabulary.
``_render``
    Fills a template from a contact row with Czech gender agreement. A contact
    whose gender is unknown only gets templates without a gender-bearing verb.
``_factory``
    Assembles the rows and stamps timestamps against ``NOTES_ANCHOR``, jittered
    backwards across a year so a rebuild is byte-identical.
``_snapshot``
    Writes the committed artifact.

**A note never invents personal data.** The PII templates quote fields the
contact already has, and one is eligible only when the contact has every field
it references — so every value in a note traces back to a contact row, which is
what lets UC-02 derive gold spans from the substrate rather than from a
detached corpus.

Import-only. The snapshot is written by ``python -m substrate.generators``.
"""

from substrate.constants import NOTE_CATEGORIES

from ._factory import NOTES_ANCHOR, generate_notes
from ._snapshot import save_snapshot

# Kept as ``CATEGORIES`` for callers that already used this name; the definition
# lives in substrate.constants so UC-03's categoriser can share it.
CATEGORIES = NOTE_CATEGORIES

__all__ = [
    "generate_notes",
    "save_snapshot",
    "NOTES_ANCHOR",
    "CATEGORIES",
]
