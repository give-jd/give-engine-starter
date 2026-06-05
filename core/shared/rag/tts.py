"""TTS (Text-to-Speech) wrapper.

Default backend: Piper via `piper-tts` Python binding.
Voci scaricate on-demand in `~/.cache/piper/`.

Backend iniettabile per test (vedi `TTSEngine(backend=...)`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.shared.rag.exceptions import RAGError


class TTSBackend(Protocol):
    def is_available(self) -> bool: ...
    def download(self) -> None: ...
    def synthesize(self, text: str) -> bytes: ...


@dataclass
class TTSConfig:
    voice: str = "it_IT-paola-medium"
    sample_rate: int = 22050


class TTSEngine:
    def __init__(
        self,
        config: TTSConfig,
        backend: TTSBackend | None = None,
    ) -> None:
        self.config = config
        self._backend = backend

    def _ensure_backend(self) -> TTSBackend:
        if self._backend is None:
            self._backend = _lazy_default_backend(self.config)
        return self._backend

    def is_available(self) -> bool:
        try:
            return self._ensure_backend().is_available()
        except Exception:
            return False

    def download_voice(self) -> None:
        try:
            self._ensure_backend().download()
        except Exception as exc:
            raise RAGError(
                f"impossibile scaricare voce Piper '{self.config.voice}': {exc}"
            ) from exc

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise RAGError("testo vuoto: niente da sintetizzare")
        backend = self._ensure_backend()
        if not backend.is_available():
            try:
                backend.download()
            except Exception as exc:
                raise RAGError(
                    f"voce Piper non disponibile e download fallito: {exc}"
                ) from exc
        try:
            return backend.synthesize(text)
        except Exception as exc:
            raise RAGError(f"sintesi vocale fallita: {exc}") from exc


def _lazy_default_backend(config: TTSConfig) -> TTSBackend:
    class _NoOpBackend:
        def is_available(self) -> bool:
            return False

        def download(self) -> None:
            raise RAGError(
                "piper-tts non installato. Installa con: pip install piper-tts"
            )

        def synthesize(self, text: str) -> bytes:
            raise RAGError("piper-tts non installato")

    try:
        import piper  # type: ignore  # noqa: F401
    except ImportError:
        return _NoOpBackend()

    class _PiperBackend:
        def __init__(self, cfg: TTSConfig) -> None:
            self.cfg = cfg
            self._voice: Any = None

        def is_available(self) -> bool:
            return self._voice is not None

        def download(self) -> None:
            from piper import PiperVoice  # type: ignore

            self._voice = PiperVoice.load(self.cfg.voice)

        def synthesize(self, text: str) -> bytes:
            if self._voice is None:
                self.download()
            import io
            import wave

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.cfg.sample_rate)
                self._voice.synthesize(text, wav)
            return buf.getvalue()

    return _PiperBackend(config)
