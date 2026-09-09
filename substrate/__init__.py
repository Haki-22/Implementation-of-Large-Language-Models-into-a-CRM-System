"""The shared synthetic CRM substrate: schema, generators, build pipeline, snapshots.

Every use case reads ``substrate/snapshots/substrate.db``, which
``substrate.pipeline.build_all`` assembles from the committed snapshots. The
package layout (``schema/``, ``generators/``, ``pipeline/``, ``constants.py``,
``lifecycle.py``) is described in ``substrate/README.md``; the database itself
in ``substrate/schema/DB.md``.

This file exists so that ``substrate`` is a regular package: without it,
setuptools' package discovery skipped the directory and a non-editable
``pip install .`` shipped ``ucs`` and ``utils`` but not the substrate
(decision D-REPO-1, 2026-09-04). It deliberately imports nothing, so that
importing a leaf such as ``substrate.constants`` stays cheap.
"""
