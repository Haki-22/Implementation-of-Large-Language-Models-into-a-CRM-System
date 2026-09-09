"""Raw public inputs of the substrate: pinned downloads and the check that fetches them.

``fetch_and_filter`` (two Amazon dumps + the 425-reviewer stratification),
``fetch_csu`` (ČSÚ population tables + Czech Post postal codes), ``_pinned``
(the shared verify / download mechanism) and ``inputs`` (one status + ensure
function over all of them, used by ``build_all`` and meant for the demo
frontend). Downloads land under ``downloaded/``; nothing else in the repository
decides about downloads.
"""
