"""One-off rule + NER fusion comparison harness for the UC-02 detector, including
the NameTag 3 adapter that runs in its own virtualenv (see ``README.md`` in this
directory). Kept as a standalone package because both scripts locate the project
root and manage their own ``sys.path`` rather than relying on the normal package
import machinery used by the rest of ``eval/``.
"""
