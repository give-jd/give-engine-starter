"""STT (Speech-to-Text) wrapper.

Default backend: Whisper.cpp via `whisper-cpp-python` (binding Python).
Modelli scaricati on-demand in `~/.cache/whisper-cpp/`.

Backend iniettabile per test (vedi `STTEngine(backend=...)`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.shared.rag.exceptions import RAGError


class STTBackend(Protocol):
    def is_available(self) -> bool: ...
    def download(self) -> None: ...
    def transcribe(self, audio_bytes: bytes) -> str: ...


@dataclass
class STTConfig:
    model: str = "base"
    language: str = "it"


class STTEngine:
    def __init__(
        self,
        config: STTConfig,
        backend: STTBackend | None = None,
    ) -> None:
        self.config = config
        self._backend = backend

    def _ensure_backend(self) -> STTBackend:
        if self._backend is None:
            self._backend = _lazy_default_backend(self.config)
        return self._backend

    def is_available(self) -> bool:
        try:
            return self._ensure_backend().is_available()
        except Exception:
            return False

    def download_model(self) -> None:
        try:
            self._ensure_backend().download()
        except Exception as exc:
            raise RAGError(
                f"impossibile scaricare modello Whisper '{self.config.model}': {exc}"
            ) from exc

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            raise RAGError("audio vuoto: niente da trascrivere")
        backend = self._ensure_backend()
        if not backend.is_available():
            try:
                backend.download()
            except Exception as exc:
                raise RAGError(
                    f"modello Whisper non disponibile e download fallito: {exc}"
                ) from exc
        try:
            return backend.transcribe(audio_bytes)
        except Exception as exc:
            raise RAGError(f"trascrizione fallita: {exc}") from exc


def _lazy_default_backend(config: STTConfig) -> STTBackend:
    class _NoOpBackend:
        def is_available(self) -> bool:
            return False

        def download(self) -> None:
            raise RAGError(
                "whisper-cpp-python non installato. "
                "Installa con: pip install whisper-cpp-python"
            )

        def transcribe(self, audio_bytes: bytes) -> str:
            raise RAGError("whisper-cpp-python non installato")

    try:
        import whisper_cpp_python  # type: ignore  # noqa: F401
    except ImportError:
        return _NoOpBackend()

    class _WhisperCppBackend:
        def __init__(self, cfg: STTConfig) -> None:
            self.cfg = cfg
            self._model: Any = None

        def is_available(self) -> bool:
            return self._model is not None

        def download(self) -> None:
            from whisper_cpp_python import Whisper  # type: ignore

            self._model = Whisper(model_path=self.cfg.model)

        def transcribe(self, audio_bytes: bytes) -> str:
            if self._model is None:
                self.download()
            result = self._model.transcribe(
                audio_bytes, language=self.cfg.language
            )
            return result.get("text", "")

    return _WhisperCppBackend(config)
