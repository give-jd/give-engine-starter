"""Exception hierarchy for the RAG module.

All RAG-specific errors inherit from `RAGError` so callers can catch
the entire module surface with a single except clause.
"""

from __future__ import annotations


class RAGError(Exception):
    """Base class for all RAG module errors."""


class ChunkingError(RAGError):
    """Raised when chunking fails (invalid strategy, malformed text, ...)."""


class EmbedderError(RAGError):
    """Raised when embedding generation fails (model load, device, ...)."""


class VectorStoreError(RAGError):
    """Raised on vector store operations (dimension mismatch, schema, ...)."""

    def __init__(
        self,
        message: str,
        *,
        expected: int | None = None,
        actual: int | None = None,
    ) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class RetrievalError(RAGError):
    """Raised when retrieval cannot complete (empty store, invalid filters)."""


class LibraryError(RAGError):
    """Raised on library loader operations (signature, download, compat)."""

    def __init__(self, message: str, *, slug: str | None = None) -> None:
        super().__init__(message)
        self.slug = slug


class LLMError(RAGError):
    """Raised on LLM client failures (auth, quota, network, parsing)."""
