"""The build chain that turns the pinned public inputs into the committed snapshots and ``substrate.db``.

Entry point: ``python -m substrate.pipeline.build_all`` (``--verify``, ``--force``,
``--from <step>``); the steps and their artifacts are described in
``substrate/pipeline/README.md``. Regular package since decision D-REPO-1
(2026-09-04): without this file setuptools skipped the whole ``pipeline``
subtree, so a non-editable install had no build chain. Imports nothing.
"""
