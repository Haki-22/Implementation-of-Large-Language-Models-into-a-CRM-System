"""NameTag 3 (ÚFAL, Czech CNEC 2.0) as a UC-02 detector, through a subprocess.

NameTag 3 ships with Keras 3 and the UFAL MorphoDiTa / UDPipe stack, which do not
coexist with the thesis virtualenv. It therefore runs in its own virtualenv and
its predictions are written to a JSONL file that the detection table reads by
``message_id``. The model and code are CC BY-NC-SA 4.0 and are not part of the
repository; ``_external/download_models.sh`` fetches them.

Run with the NameTag 3 interpreter, from the project root::

    <venv-nametag3>/bin/python -m ucs.uc02_pseudonymization.eval.nametag3_adapter \\
        --out eval/runs/<run>/nametag3_predictions.jsonl

The reproduction recipe for the virtualenv is in ``eval/fusion_refresh/README.md``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from utils.paths import UC02_DIR, UC02_PII_CORPUS_SNAPSHOT

# ---------------------------------------------------------------------------
# External assets
# ---------------------------------------------------------------------------

NAMETAG3_EXT = UC02_DIR / "_external"
NAMETAG3_MODEL_DIR = NAMETAG3_EXT / "nametag3/nametag3-czech-cnec2.0-240830"
NAMETAG3_CODE_DIR = NAMETAG3_EXT / "nametag3-code"
UDPIPE_FILE = NAMETAG3_MODEL_DIR / "udpipe.tokenizer"


def verify_nametag3_assets() -> None:
    """Fail fast with an actionable message if the NameTag 3 assets are missing."""
    missing: list[str] = []
    if not UDPIPE_FILE.exists():
        missing.append(f"  - UDPipe tokenizer: {UDPIPE_FILE}")
    if not (NAMETAG3_MODEL_DIR / "checkpoint.weights.h5").exists():
        missing.append(f"  - Model weights: {NAMETAG3_MODEL_DIR}/checkpoint.weights.h5")
    if not (NAMETAG3_CODE_DIR / "nametag3.py").exists():
        missing.append(f"  - NameTag 3 code: {NAMETAG3_CODE_DIR}/nametag3.py")
    if missing:
        installer = NAMETAG3_EXT / "download_models.sh"
        raise FileNotFoundError(
            "NameTag 3 external assets are missing:\n"
            + "\n".join(missing)
            + f"\n\nRun: {installer}\n"
            "(downloads the model weights from LINDAT and clones github.com/ufal/nametag3; "
            "~488 MB; CC BY-NC-SA 4.0, academic use only.)"
        )


# ---------------------------------------------------------------------------
# Label mapping: CNEC 2.0 fine-grained labels -> UC-02 types
# ---------------------------------------------------------------------------

# CNEC 2.0 emits 46 atomic types, 7 supertypes and 4 containers. The first
# letter of a label is its supertype; a few fine-grained labels map more
# precisely. Anything not personal data maps to ``_skip``.
LABEL_MAP_PREFIXES: dict[str, str] = {
    "p": "PERSON",
    "P": "PERSON",
    "i": "ORG",
    "I": "ORG",
    "g": "ADDRESS",
    "G": "ADDRESS",
    "a": "ADDRESS",
    "A": "ADDRESS",
    "t": "DATE",
    "T": "DATE",
    "n": "_skip",
    "o": "_skip",
    "O": "_skip",
    "m": "_skip",
    "M": "_skip",
}

SPECIFIC_LABEL_MAP: dict[str, str] = {
    "ah": "ADDRESS",  # house number
    "az": "PSC",  # postal code
    "at": "PHONE",  # phone
    "io": "ORG",
    "ic": "ORG",
    "ia": "ORG",
    "if": "ORG",
    "ig": "ORG",
    "pf": "PERSON",  # first name
    "ps": "PERSON",  # surname
    "ph": "PERSON",
    "pm": "PERSON",
    "pp": "PERSON",
    "tf": "DATE",
    "tm": "DATE",
    "ty": "DATE",
    "td": "DATE",
    "th": "DATE",
    "gc": "ADDRESS",
    "gh": "ADDRESS",
    "gl": "ADDRESS",
    "gq": "ADDRESS",
    "gr": "ADDRESS",
    "gs": "ADDRESS",  # street
    "gt": "ADDRESS",
    "gu": "ADDRESS",  # urban
    "n_": "_skip",
    "na": "_skip",
}


def normalize_nametag_label(raw: str) -> str:
    """Map one CNEC 2.0 label to a UC-02 type, ``_skip`` or ``_unknown``."""
    if not raw or raw == "O":
        return "_skip"
    if "-" in raw:
        raw = raw.split("-", 1)[1]
    if raw in SPECIFIC_LABEL_MAP:
        return SPECIFIC_LABEL_MAP[raw]
    if raw and raw[0] in LABEL_MAP_PREFIXES:
        return LABEL_MAP_PREFIXES[raw[0]]
    return "_unknown"


# ---------------------------------------------------------------------------
# Tokenisation, inference, span reconstruction
# ---------------------------------------------------------------------------


def tokenize_with_udpipe(sentences: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Tokenise each text with the bundled UDPipe model.

    Returns one token list per input; a token is ``{form, start, end}`` with
    character offsets into the original text.
    """
    from ufal.udpipe import Model, Pipeline, ProcessingError

    if not UDPIPE_FILE.exists():
        raise FileNotFoundError(f"UDPipe tokenizer not found at {UDPIPE_FILE}")
    model = Model.load(str(UDPIPE_FILE))
    if not model:
        raise RuntimeError("UDPipe Model.load returned None")
    pipeline = Pipeline(model, "tokenize", Pipeline.NONE, Pipeline.NONE, "conllu")

    out: list[list[dict[str, Any]]] = []
    for s in sentences:
        text = s["text"]
        error = ProcessingError()
        conllu = pipeline.process(text, error)
        if error.occurred():
            print(f"WARN UDPipe error on {s['id']}: {error.message}", file=sys.stderr)
        tokens: list[dict[str, Any]] = []
        cursor = 0
        for line in conllu.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 2 or "-" in cols[0]:
                continue
            form = cols[1]
            idx = text.find(form, cursor)
            if idx < 0:
                idx = text.find(form)
            if idx < 0:
                continue
            tokens.append({"form": form, "start": idx, "end": idx + len(form)})
            cursor = idx + len(form)
        out.append(tokens)
    return out


def write_conll(tokens_per_sentence: list[list[dict[str, Any]]], path: Path) -> None:
    """Write one token per line, a blank line between texts (NameTag 3 input)."""
    with path.open("w", encoding="utf-8") as f:
        for tokens in tokens_per_sentence:
            for t in tokens:
                f.write(t["form"] + "\n")
            f.write("\n")


def run_nametag3(conll_in: Path) -> list[list[str]]:
    """Invoke ``nametag3.py`` as a subprocess; return the BIO labels per text."""
    cmd = [
        sys.executable,
        str(NAMETAG3_CODE_DIR / "nametag3.py"),
        f"--load_checkpoint={NAMETAG3_MODEL_DIR}/",
        f"--test_data={conll_in}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(NAMETAG3_CODE_DIR))
    if proc.returncode != 0:
        print("STDERR:", proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"nametag3 returned {proc.returncode}")
    sentences_labels: list[list[str]] = []
    current: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            if current:
                sentences_labels.append(current)
                current = []
            continue
        cols = line.split("\t")
        current.append(cols[1] if len(cols) >= 2 else "O")
    if current:
        sentences_labels.append(current)
    return sentences_labels


def bio_to_spans(tokens: list[dict[str, Any]], labels: list[str]) -> list[dict[str, Any]]:
    """Reconstruct character spans from BIO-tagged tokens.

    NameTag 3 stacks nested labels with ``|``; the first (outermost) part is
    used because it is the more general type.
    """
    spans: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for tok, label in zip(tokens, labels):
        primary = label.split("|")[0] if label else "O"
        if primary == "O":
            if current:
                spans.append(current)
                current = None
            continue
        prefix = primary.split("-", 1)[0] if "-" in primary else ""
        entity = primary.split("-", 1)[1] if "-" in primary else primary
        if prefix == "I" and current and current["raw_label"] == entity:
            current["end"] = tok["end"]
            continue
        if current:
            spans.append(current)
        current = {"start": tok["start"], "end": tok["end"], "raw_label": entity}
    if current:
        spans.append(current)
    return spans


# ---------------------------------------------------------------------------
# Corpus prediction
# ---------------------------------------------------------------------------


def predict_corpus(corpus: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], float]:
    """Run NameTag 3 over a corpus; return predictions by ``message_id`` and the seconds taken."""
    verify_nametag3_assets()
    sentences = [{"id": m["message_id"], "text": m["text"]} for m in corpus]
    tokens_per_sentence = tokenize_with_udpipe(sentences)
    with tempfile.TemporaryDirectory() as td:
        conll_path = Path(td) / "input.conll"
        write_conll(tokens_per_sentence, conll_path)
        t0 = time.monotonic()
        labels_per_sentence = run_nametag3(conll_path)
        elapsed = time.monotonic() - t0
    if len(labels_per_sentence) != len(sentences):
        print(
            f"WARN sentence count mismatch: input={len(sentences)} output={len(labels_per_sentence)}",
            file=sys.stderr,
        )
    predictions: dict[str, list[dict[str, Any]]] = {}
    for s, tokens, labels in zip(sentences, tokens_per_sentence, labels_per_sentence):
        n = min(len(tokens), len(labels))
        msg_spans: list[dict[str, Any]] = []
        for sp in bio_to_spans(tokens[:n], labels[:n]):
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
                    "ner_confidence": 1.0,
                    "source": "ner:nametag3",
                }
            )
        predictions[s["id"]] = msg_spans
    return predictions, elapsed


def load_predictions(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read a predictions JSONL written by :func:`main` into ``{message_id: spans}``."""
    cache: dict[str, list[dict[str, Any]]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                cache[row["message_id"]] = row["spans"]
    return cache


def main(argv: list[str] | None = None) -> None:
    """CLI: predict the corpus and write one JSONL row per message."""
    parser = argparse.ArgumentParser(description="NameTag 3 predictions for the UC-02 corpus.")
    parser.add_argument("--corpus", default=str(UC02_PII_CORPUS_SNAPSHOT))
    parser.add_argument("--out", required=True, help="Predictions JSONL path.")
    args = parser.parse_args(argv)
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    predictions, elapsed = predict_corpus(corpus)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for mid, spans in predictions.items():
            f.write(json.dumps({"message_id": mid, "spans": spans}, ensure_ascii=False) + "\n")
    total = sum(len(v) for v in predictions.values())
    print(f"NameTag 3: {len(corpus)} messages, {total} detections, {elapsed:.1f} s -> {out}")


if __name__ == "__main__":
    main()
