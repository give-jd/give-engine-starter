"""Tests for STTEngine (Whisper.cpp wrapper)."""

from __future__ import annotations

import pytest

from core.shared.rag.exceptions import RAGError
from core.shared.rag.stt import STTConfig, STTEngine


class _FakeSTTBackend:
    def __init__(self, model: str, language: str):
        self.model = model
        self.language = language
        self.downloaded = True
        self.transcribed_texts: list[bytes] = []

    def is_available(self) -> bool:
        return self.downloaded

    def download(self) -> None:
        self.downloaded = True

    def transcribe(self, audio_bytes: bytes) -> str:
        self.transcribed_texts.append(audio_bytes)
        return f"transcribed: {len(audio_bytes)} bytes"


class TestSTTConfig:
    def test_default_config(self):
        cfg = STTConfig()
        assert cfg.model == "base"
        assert cfg.language == "it"

    def test_custom_config(self):
        cfg = STTConfig(model="small", language="en")
        assert cfg.model == "small"
        assert cfg.language == "en"


class TestSTTEngine:
    def test_engine_uses_injected_backend(self):
        backend = _FakeSTTBackend(model="base", language="it")
        engine = STTEngine(STTConfig(), backend=backend)
        assert engine.is_available() is True

    def test_transcribe_returns_string(self):
        backend = _FakeSTTBackend(model="base", language="it")
        engine = STTEngine(STTConfig(), backend=backend)
        result = engine.transcribe(b"fake audio bytes")
        assert isinstance(result, str)
        assert "transcribed" in result

    def test_transcribe_empty_audio_raises(self):
        backend = _FakeSTTBackend(model="base", language="it")
        engine = STTEngine(STTConfig(), backend=backend)
        with pytest.raises(RAGError):
            engine.transcribe(b"")

    def test_unavailable_backend_triggers_download(self):
        backend = _FakeSTTBackend(model="base", language="it")
        backend.downloaded = False
        engine = STTEngine(STTConfig(), backend=backend)
        assert engine.is_available() is False
        engine.download_model()
        assert engine.is_available() is True

    def test_transcribe_without_model_auto_downloads(self):
        backend = _FakeSTTBackend(model="base", language="it")
        backend.downloaded = False
        engine = STTEngine(STTConfig(), backend=backend)
        text = engine.transcribe(b"audio")
        assert "transcribed" in text
        assert backend.downloaded is True


class TestLazyDefaultBackend:
    def test_unconfigured_backend_lazy_loads_on_call(self):
        engine = STTEngine(STTConfig())
        result = engine.is_available()
        assert isinstance(result, bool)
