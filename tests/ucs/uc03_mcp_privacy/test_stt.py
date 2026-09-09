"""Speech to text: WAV validation, backend selection, the switch on cloud backends, Whisper on silence."""

from __future__ import annotations

import wave

import pytest

from ucs.uc03_mcp_privacy import config, stt


def _write_wav(path, *, rate=16000, channels=1, sampwidth=2, seconds=1.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(b"\x00" * sampwidth * channels * int(rate * seconds))


def test_read_wav_pcm_rejects_other_formats(tmp_path):
    _write_wav(tmp_path / "rate.wav", rate=8000)
    with pytest.raises(ValueError, match="Hz"):
        stt.read_wav_pcm(tmp_path / "rate.wav")
    _write_wav(tmp_path / "stereo.wav", channels=2)
    with pytest.raises(ValueError, match="channel"):
        stt.read_wav_pcm(tmp_path / "stereo.wav")
    _write_wav(tmp_path / "wide.wav", sampwidth=4)
    with pytest.raises(ValueError, match="byte"):
        stt.read_wav_pcm(tmp_path / "wide.wav")


def test_write_and_read_round_trip(tmp_path):
    pcm = bytes(range(256)) * 8
    out = stt.write_wav(tmp_path / "x.wav", pcm)
    assert stt.read_wav_pcm(out) == pcm


def test_unknown_backend_is_refused():
    with pytest.raises(ValueError, match="unknown STT backend"):
        stt.transcribe_pcm(b"\x00\x00" * 16000, backend="azure")


def test_cloud_backends_fail_closed_without_the_switch(monkeypatch):
    monkeypatch.setenv("THESIS_LLM_CALLS", "FALSE")
    with pytest.raises(Exception, match="THESIS_LLM_CALLS"):
        stt.transcribe_pcm(b"\x00\x00" * 16000, backend="google-web")
    with pytest.raises(Exception, match="THESIS_LLM_CALLS"):
        stt.transcribe_pcm(b"\x00\x00" * 16000, backend="google-cloud")


def test_whisper_tiny_transcribes_silence(tmp_path):
    if not (config.MODEL_DIR / "models--Systran--faster-whisper-tiny").exists():
        pytest.skip("faster-whisper tiny is not cached locally")
    _write_wav(tmp_path / "silence.wav", seconds=1.0)
    text = stt.transcribe_file(tmp_path / "silence.wav", backend="whisper", model_size="tiny")
    assert isinstance(text, str)
