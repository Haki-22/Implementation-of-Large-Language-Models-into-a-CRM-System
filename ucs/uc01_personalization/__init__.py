"""UC-01: personalised Czech outreach, one contact, one brief, one level at a time.

The unit is :func:`generate` (``generate.py``): it reads the contact and the
level's inputs from ``substrate.db``, builds that level's prompt, dispatches
through ``utils.generation`` behind the ``THESIS_LLM_CALLS`` switch, and judges
the text. The ladder of levels is in ``levels.py``, the Czech prompt text in
``prompts.py``, the judges in ``judge.py``. ``picker.py`` chooses who the reported
runs are for and writes it down; ``runner.py`` loops a pick and writes one
folder per run; ``metrics.py`` scores a run. ``python -m ucs.uc01_personalization``
is the command line; the frontend calls :func:`generate` for live generation.
"""

from ucs.uc01_personalization.generate import Generation, generate, generate_sync
from ucs.uc01_personalization.levels import LADDER, LEVELS

__all__ = ["Generation", "generate", "generate_sync", "LADDER", "LEVELS"]
