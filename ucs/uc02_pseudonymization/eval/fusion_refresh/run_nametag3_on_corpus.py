"""NameTag 3 on the UC-02 69-message PII corpus.

Runs UDPipe tokenization + NameTag 3 subprocess inference + BIO span reconstruction
on each message in ``uc02-pii-corpus.json``. Writes per-message predictions to
``nametag3_predictions.jsonl`` for the main harness to consume.

MUST be invoked with the dedicated venv-nametag3 Python interpreter:

    <venv-nametag3>/bin/python -m \\
        ucs.uc02_pseudonymization.eval.fusion_refresh.run_nametag3_on_corpus

Where ``<venv-nametag3>`` is created per the reproduction recipe in
``ucs/uc02_pseudonymization/eval/fusion_refresh/README.md`` (a fresh-clone user
typically places it next to the main ``.venv`` at the repo root).

Why a separate venv: NameTag 3 ships with Keras 3 + UFAL MorphoDiTa + UDPipe that
conflict with the main venv ML stack.

This adapter reuses the BIO → span normalization machinery from
``ner_smoke_runner_nametag3.py`` but reads the production 69-message corpus
instead of the 30-sentence smoke seed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path


def _find_thesis_root(start: Path) -> Path:
    """Walk up the directory tree until a folder that holds ``ucs/uc02_pseudonymization``,
    directly or under a ``thesis`` subfolder (the layout this harness was written for),
    is found. The env var ``THESIS_ROOT`` overrides the search entirely. See
    ``fusion_refresh_harness.py`` for rationale."""
    import os

    env_override = os.environ.get("THESIS_ROOT")
    if env_override:
        candidate = Path(env_override).resolve()
        if (candidate / "ucs" / "uc02_pseudonymization").is_dir():
            return candidate
    here = start.resolve()
    for _ in range(8):
        candidate = here / "thesis"
        if (candidate / "ucs" / "uc02_pseudonymization").is_dir():
            return candidate
        if here.parent == here:
            break
        here = here.parent
    raise RuntimeError(
        f"Could not locate ucs/uc02_pseudonymization from {start}. "
        f"Set the THESIS_ROOT env var to the project root."
    )


THESIS_ROOT = _find_thesis_root(Path(__file__))
sys.path.insert(0, str(THESIS_ROOT))

from ucs.uc02_pseudonymization.eval.ner_smoke_runner_nametag3 import (  # noqa: E402
    _verify_nametag3_assets,
    bio_to_spans,
    normalize_nametag_label,
    run_nametag3,
    tokenize_with_udpipe,
    write_conll,
)

from utils.paths import UC02_PII_CORPUS_SNAPSHOT  # noqa: E402

CORPUS = UC02_PII_CORPUS_SNAPSHOT
OUT_PATH = Path(__file__).resolve().parent / "nametag3_predictions.jsonl"


def main() -> None:
    """Tokenize the corpus, run NameTag 3 and write per-message predictions to `OUT_PATH`."""
    _verify_nametag3_assets()
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    # Adapt corpus shape to what the runner expects: id + text fields.
    sentences = [{"id": m["message_id"], "text": m["text"]} for m in corpus]
    print(f"Loaded {len(sentences)} messages")

    print("Tokenizing with UDPipe...")
    tokens_per_sentence = tokenize_with_udpipe(sentences)

    with tempfile.TemporaryDirectory() as td:
        conll_path = Path(td) / "input.conll"
        write_conll(tokens_per_sentence, conll_path)
        print(f"CoNLL input written to {conll_path}")

        t0 = time.monotonic()
        labels_per_sentence = run_nametag3(conll_path)
        elapsed = time.monotonic() - t0

    if len(labels_per_sentence) != len(sentences):
        print(
            f"WARN sentence count mismatch: input={len(sentences)} "
            f"output={len(labels_per_sentence)}"
        )

    predictions: dict[str, list[dict]] = {}
    for s, tokens, labels in zip(sentences, tokens_per_sentence, labels_per_sentence):
        n = min(len(tokens), len(labels))
        spans = bio_to_spans(tokens[:n], labels[:n])
        msg_spans: list[dict] = []
        for sp in spans:
            norm = normalize_nametag_label(sp["raw_label"])
            if norm in ("_skip", "_unknown"):
                continue
            msg_spans.append(
                {
                    "span_start": sp["start"],
                    "span_end": sp["end"],
                    "pii_type": norm,
                    "surface_form": s["text"][sp["start"] : sp["end"]],
                    "raw_label": sp["raw_label"],
                }
            )
        predictions[s["id"]] = msg_spans

    print(f"Inference time: {elapsed:.2f}s ({elapsed / len(sentences):.3f}s/msg)")
    total = sum(len(v) for v in predictions.values())
    print(f"Total NameTag 3 detections (after filtering): {total}")

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for mid, spans in predictions.items():
            f.write(json.dumps({"message_id": mid, "spans": spans}, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
