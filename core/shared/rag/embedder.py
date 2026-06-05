"""Embeddings wrapper around sentence-transformers.

Designed to be testable without downloading the real ~1 GB model: callers
(and tests) may inject `encoder_fn` and `dimension` to bypass model loading.
Production callers use the default constructor which lazily loads
sentence-transformers on first encode.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.shared.rag.chunking import Chunk
from core.shared.rag.exceptions import EmbedderError


# Known model → dimension. Allows compatibility checks without loading the
# model (used by library_loader to reject incompatible skills).
_KNOWN_DIMENSIONS: dict[str, int] = {
    "intfloat/multilingual-e5-base": 768,
    "multilingual-e5-base": 768,
    "BAAI/bge-m3": 1024,
    "bge-m3": 1024,
}


EncoderFn = Callable[[list[str], int], np.ndarray]
ProgressCallback = Callable[[int, int], None]


def _detect_device() -> str:
    """Best-effort device detection. Falls back to CPU if torch missing."""
    try:
        import torch  # type: ignore
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class EmbedderConfig:
    model_name: str
    cache_dir: Path | None = None
    device: str | None = None

    def resolve_device(self) -> str:
        return self.device if self.device else _detect_device()

    def resolve_cache_dir(self) -> Path:
        if self.cache_dir is not None:
            return Path(self.cache_dir)
        return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))


class Embedder:
    def __init__(
        self,
        config: EmbedderConfig,
        encoder_fn: EncoderFn | None = None,
        dimension: int | None = None,
    ) -> None:
        self.config = config
        self.device = config.resolve_device()
        self._encoder_fn = encoder_fn
        self._model: Any = None  # sentence_transformers.SentenceTransformer

        if dimension is not None:
            self._dimension = dimension
        elif config.model_name in _KNOWN_DIMENSIONS:
            self._dimension = _KNOWN_DIMENSIONS[config.model_name]
        else:
            self._dimension = -1  # discovered on first encode

    @property
    def dimension(self) -> int:
        if self._dimension > 0:
            return self._dimension
        self._encode(["x"])
        return self._dimension

    def embed_query(self, query: str) -> np.ndarray:
        arr = self._encode([query])
        return arr[0]

    def embed_chunks(
        self,
        chunks: list[Chunk],
        batch_size: int = 32,
        progress_callback: ProgressCallback | None = None,
    ) -> list[np.ndarray]:
        if not chunks:
            return []
        if batch_size <= 0:
            raise EmbedderError(f"batch_size must be > 0, got {batch_size}")

        total = len(chunks)
        result: list[np.ndarray] = []
        for start in range(0, total, batch_size):
            batch_texts = [c.text for c in chunks[start : start + batch_size]]
            arr = self._encode(batch_texts)
            result.extend(arr[i] for i in range(arr.shape[0]))
            if progress_callback is not None:
                progress_callback(min(start + batch_size, total), total)
        return result

    def _encode(self, texts: list[str]) -> np.ndarray:
        encoder = self._encoder_fn or self._lazy_default_encoder()
        try:
            arr = encoder(texts, 32)
        except Exception as exc:
            raise EmbedderError(f"encoder failed: {exc}") from exc
        if not isinstance(arr, np.ndarray) or arr.ndim != 2:
            raise EmbedderError(
                f"encoder returned unexpected shape: {getattr(arr, 'shape', None)}"
            )
        if self._dimension <= 0:
            self._dimension = int(arr.shape[1])
        elif arr.shape[1] != self._dimension:
            raise EmbedderError(
                f"encoder returned dim {arr.shape[1]}, expected {self._dimension}"
            )
        return arr.astype(np.float32, copy=False)

    def _lazy_default_encoder(self) -> EncoderFn:
        """Load sentence-transformers on first call.

        Embeddings are L2-normalized so that L2 distance from sqlite-vec maps
        cleanly to cosine similarity.
        """
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise EmbedderError(
                "sentence-transformers not installed — run "
                "`pip install -r requirements-rag.txt`"
            ) from exc

        cache_dir = self.config.resolve_cache_dir()
        self._model = SentenceTransformer(
            self.config.model_name,
            device=self.device,
            cache_folder=str(cache_dir),
        )

        def _encode(texts: list[str], batch_size: int) -> np.ndarray:
            arr = self._model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return np.asarray(arr, dtype=np.float32)

        self._encoder_fn = _encode
        return _encode
