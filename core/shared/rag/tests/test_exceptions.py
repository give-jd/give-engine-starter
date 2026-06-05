"""Tests for exception hierarchy."""

import pytest

from core.shared.rag.exceptions import (
    ChunkingError,
    EmbedderError,
    LibraryError,
    LLMError,
    RAGError,
    RetrievalError,
    VectorStoreError,
)


class TestRAGErrorHierarchy:
    def test_rag_error_is_base(self):
        assert issubclass(RAGError, Exception)

    @pytest.mark.parametrize(
        "subclass",
        [
            ChunkingError,
            EmbedderError,
            VectorStoreError,
            RetrievalError,
            LibraryError,
            LLMError,
        ],
    )
    def test_all_subclasses_inherit_from_rag_error(self, subclass):
        assert issubclass(subclass, RAGError)

    def test_chunking_error_carries_message(self):
        err = ChunkingError("invalid strategy: foo")
        assert "invalid strategy: foo" in str(err)

    def test_vector_store_error_carries_context(self):
        err = VectorStoreError(
            "dimension mismatch", expected=768, actual=1024
        )
        assert err.expected == 768
        assert err.actual == 1024
        assert "dimension mismatch" in str(err)

    def test_library_error_carries_skill_slug(self):
        err = LibraryError("signature invalid", slug="manuali-anthropic")
        assert err.slug == "manuali-anthropic"

    def test_rag_error_catches_all_subclasses(self):
        with pytest.raises(RAGError):
            raise ChunkingError("x")
        with pytest.raises(RAGError):
            raise EmbedderError("y")
        with pytest.raises(RAGError):
            raise LLMError("z")
