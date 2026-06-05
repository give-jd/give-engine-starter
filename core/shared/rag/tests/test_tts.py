"""Tests for TTSEngine (Piper wrapper)."""

from __future__ import annotations

import struct

import pytest

from core.shared.rag.exceptions import RAGError
from core.shared.rag.tts import TTSConfig, TTSEngine


class _FakeTTSBackend:
    def __init__(self, voice: str):
        self.voice = voice
        self.downloaded = True
        self.synthesized_texts: list[str] = []

    def is_available(self) -> bool:
        return self.downloaded

    def download(self) -> None:
        self.downloaded = True

    def synthesize(self, text: str) -> bytes:
        self.synthesized_texts.append(text)
        return b"RIFF" + struct.pack("<I", 36 + len(text)) + b"WAVE" + text.encode()


class TestTTSConfig:
    def test_default_config(self):
        cfg = TTSConfig()
        assert "it_IT" in cfg.voice
        assert cfg.sample_rate > 0

    def test_custom_voice(self):
        cfg = TTSConfig(voice="it_IT-paola-medium")
        assert cfg.voice == "it_IT-paola-medium"


class TestTTSEngine:
    def test_engine_uses_injected_backend(self):
        backend = _FakeTTSBackend(voice="it_IT-paola-medium")
        engine = TTSEngine(TTSConfig(), backend=backend)
        assert engine.is_available() is True

    def test_synthesize_returns_wav_bytes(self):
        backend = _FakeTTSBackend(voice="it_IT-paola-medium")
        engine = TTSEngine(TTSConfig(), backend=backend)
        wav = engine.synthesize("Ciao, sono Atheneo.")
        assert isinstance(wav, bytes)
        assert wav.startswith(b"RIFF")

    def test_synthesize_empty_text_raises(self):
        backend = _FakeTTSBackend(voice="it_IT-paola-medium")
        engine = TTSEngine(TTSConfig(), backend=backend)
        with pytest.raises(RAGError):
            engine.synthesize("")
        with pytest.raises(RAGError):
            engine.synthesize("   ")

    def test_unavailable_backend_triggers_download(self):
        backend = _FakeTTSBackend(voice="it_IT-paola-medium")
        backend.downloaded = False
        engine = TTSEngine(TTSConfig(), backend=backend)
        assert engine.is_available() is False
        engine.download_voice()
        assert engine.is_available() is True

    def test_synthesize_without_voice_auto_downloads(self):
        backend = _FakeTTSBackend(voice="it_IT-paola-medium")
        backend.downloaded = False
        engine = TTSEngine(TTSConfig(), backend=backend)
        wav = engine.synthesize("Ciao")
        assert wav.startswith(b"RIFF")
        assert backend.downloaded is True


class TestLazyDefaultBackend:
    def test_unconfigured_backend_lazy_loads_on_call(self):
        engine = TTSEngine(TTSConfig())
        result = engine.is_available()
        assert isinstance(result, bool)
