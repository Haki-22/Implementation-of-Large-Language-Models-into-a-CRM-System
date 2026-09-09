"""Speech to text for the UC-03 chat.

Local ``faster-whisper`` is the default: the recording never leaves the machine,
which is the property the privacy story of UC-03 rests on. Two Google backends
exist for the local-versus-cloud comparison only; both send the audio to Google
and both refuse to run unless the global model-call switch is on
(``utils.llm_switch``), exactly like every other external call in this
repository.

Functions
---------
- ``record_pcm`` - push-to-talk capture from the default microphone through
  PulseAudio's ``parec`` (16 kHz, mono, 16-bit); stops on Enter or after a
  maximum duration.
- ``transcribe_pcm`` / ``transcribe_file`` - raw PCM bytes or a WAV file in
  the same format to Czech text with the chosen backend.

CLI
---
    python -m ucs.uc03_mcp_privacy.stt --file clip.wav [--backend whisper] [--model medium]
    python -m ucs.uc03_mcp_privacy.stt --record [--seconds 20]

Convert other audio to the expected WAV shape with
``ffmpeg -i input.m4a -ar 16000 -ac 1 -sample_fmt s16 output.wav``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

from ucs.uc03_mcp_privacy import config

# ---------------------------------------------------------------------------
# Whisper (local)
# ---------------------------------------------------------------------------

_WHISPER_MODELS: dict[str, Any] = {}
_WHISPER_LOCK = threading.Lock()


def load_whisper_vocab() -> str | None:
    """Return the Czech CRM vocabulary of ``vocab_cs.txt`` as one prompt string, or None."""
    path = config.WHISPER_VOCAB_FILE
    if not path.exists():
        return None
    tokens = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return ", ".join(tokens) if tokens else None


def _whisper_model(model_size: str) -> Any:
    """Return the cached `faster_whisper.WhisperModel` for `model_size`, loading it on first use."""
    with _WHISPER_LOCK:
        model = _WHISPER_MODELS.get(model_size)
        if model is None:
            from faster_whisper import WhisperModel

            model = WhisperModel(
                model_size,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
                download_root=str(config.MODEL_DIR),
            )
            _WHISPER_MODELS[model_size] = model
        return model


def _whisper_transcribe(pcm: bytes, model_size: str) -> str:
    """Transcribe 16 kHz mono 16-bit PCM locally with `faster-whisper`, CRM vocabulary as the prompt."""
    import numpy as np

    audio = np.frombuffer(pcm, np.int16).flatten().astype(np.float32) / 32768.0
    kwargs: dict[str, Any] = {
        "beam_size": config.WHISPER_BEAM_SIZE,
        "language": config.WHISPER_LANGUAGE,
        "vad_filter": True,
    }
    prompt = load_whisper_vocab()
    if prompt:
        kwargs["initial_prompt"] = prompt
    segments, _info = _whisper_model(model_size).transcribe(audio, **kwargs)
    return "".join(segment.text for segment in segments).strip()


# ---------------------------------------------------------------------------
# Google (cloud, comparison only, behind the switch)
# ---------------------------------------------------------------------------


def _google_web_transcribe(pcm: bytes) -> str:
    """Transcribe via the free Google Web Speech API (comparison only; gated by the model-call switch)."""
    from utils.llm_switch import require_llm_calls

    require_llm_calls("google-web-stt")
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    audio = sr.AudioData(pcm, config.SAMPLE_RATE, config.SAMPLE_WIDTH_BYTES)
    return recognizer.recognize_google(audio, language=config.GOOGLE_WEB_LANGUAGE).strip()


def _google_cloud_transcribe(pcm: bytes) -> str:
    """Transcribe via Google Cloud Speech-to-Text v2 (comparison only; gated by the model-call switch)."""
    from utils.llm_switch import require_llm_calls

    require_llm_calls("google-cloud-stt")
    if not config.GOOGLE_CLOUD_PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT (or GOOGLE_CLOUD_PROJECT_ID) is not set")
    from google.cloud import speech_v2 as speech

    client = speech.SpeechClient()
    recognizer = (
        f"projects/{config.GOOGLE_CLOUD_PROJECT_ID}/locations/{config.GOOGLE_CLOUD_LOCATION}"
        f"/recognizers/{config.GOOGLE_CLOUD_RECOGNIZER}"
    )
    recognition_config = speech.RecognitionConfig(
        explicit_decoding_config=speech.ExplicitDecodingConfig(
            encoding=speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=config.SAMPLE_RATE,
            audio_channel_count=config.CHANNELS,
        ),
        language_codes=[config.GOOGLE_CLOUD_LANGUAGE],
        model=config.GOOGLE_CLOUD_MODEL,
    )
    response = client.recognize(
        request=speech.RecognizeRequest(
            recognizer=recognizer, config=recognition_config, content=pcm
        )
    )
    parts = [r.alternatives[0].transcript for r in response.results if r.alternatives]
    return " ".join(p.strip() for p in parts if p.strip()).strip()


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def transcribe_pcm(
    pcm: bytes,
    *,
    backend: str = config.DEFAULT_STT_BACKEND,
    model_size: str = config.WHISPER_MODEL,
) -> str:
    """Transcribe 16 kHz mono 16-bit PCM with ``whisper`` (local), ``google-web`` or ``google-cloud``."""
    name = backend.strip().lower()
    if name == "whisper":
        return _whisper_transcribe(pcm, model_size)
    if name == "google-web":
        return _google_web_transcribe(pcm)
    if name == "google-cloud":
        return _google_cloud_transcribe(pcm)
    raise ValueError(f"unknown STT backend {backend!r}; choices: {config.STT_BACKENDS}")


def read_wav_pcm(path: str | Path) -> bytes:
    """Return the PCM frames of a WAV file, refusing anything but 16 kHz mono 16-bit."""
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != config.SAMPLE_RATE:
            raise ValueError(f"expected {config.SAMPLE_RATE} Hz, got {wav.getframerate()} Hz")
        if wav.getnchannels() != config.CHANNELS:
            raise ValueError(f"expected {config.CHANNELS} channel(s), got {wav.getnchannels()}")
        if wav.getsampwidth() != config.SAMPLE_WIDTH_BYTES:
            raise ValueError(
                f"expected {config.SAMPLE_WIDTH_BYTES}-byte samples, got {wav.getsampwidth()}-byte"
            )
        return wav.readframes(wav.getnframes())


def transcribe_file(
    audio_path: str | Path,
    *,
    backend: str = config.DEFAULT_STT_BACKEND,
    model_size: str = config.WHISPER_MODEL,
) -> str:
    """Transcribe one WAV file (16 kHz mono 16-bit PCM) with the chosen backend."""
    return transcribe_pcm(read_wav_pcm(Path(audio_path)), backend=backend, model_size=model_size)


def record_pcm(
    max_seconds: float = config.RECORD_MAX_SECONDS, *, wait_for_enter: bool = True
) -> bytes:
    """Record from the default microphone until Enter is pressed or ``max_seconds`` pass.

    Uses PulseAudio's ``parec``; raises ``RuntimeError`` with a hint when it is
    missing. Returns raw 16 kHz mono 16-bit PCM.
    """
    try:
        proc = subprocess.Popen(
            [
                "parec",
                "--format=s16le",
                f"--rate={config.SAMPLE_RATE}",
                f"--channels={config.CHANNELS}",
                "--latency-msec=100",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "parec (PulseAudio) is not installed; record a WAV another way and pass --file"
        ) from exc
    stop = threading.Event()
    if wait_for_enter:
        threading.Thread(target=lambda: (sys.stdin.readline(), stop.set()), daemon=True).start()
    chunks: list[bytes] = []
    started = time.monotonic()
    assert proc.stdout is not None
    try:
        while not stop.is_set() and time.monotonic() - started < max_seconds:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    return b"".join(chunks)


def write_wav(path: str | Path, pcm: bytes) -> Path:
    """Save PCM bytes as a WAV file in the pipeline's format (for the eval corpus, for replay)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(config.CHANNELS)
        wav.setsampwidth(config.SAMPLE_WIDTH_BYTES)
        wav.setframerate(config.SAMPLE_RATE)
        wav.writeframes(pcm)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: transcribe a WAV file or a fresh recording."""
    parser = argparse.ArgumentParser(description="UC-03 speech to text")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="WAV file, 16 kHz mono 16-bit PCM")
    source.add_argument("--record", action="store_true", help="record from the microphone")
    parser.add_argument("--seconds", type=float, default=config.RECORD_MAX_SECONDS)
    parser.add_argument(
        "--backend", choices=config.STT_BACKENDS, default=config.DEFAULT_STT_BACKEND
    )
    parser.add_argument("--model", default=config.WHISPER_MODEL, help="Whisper size (whisper only)")
    parser.add_argument("--save", help="also save the recording as this WAV file")
    args = parser.parse_args(argv)

    if args.record:
        print(f"Recording... press Enter to stop (max {args.seconds:.0f} s)", file=sys.stderr)
        pcm = record_pcm(args.seconds)
        if args.save:
            write_wav(args.save, pcm)
    else:
        pcm = read_wav_pcm(args.file)
    print(transcribe_pcm(pcm, backend=args.backend, model_size=args.model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
