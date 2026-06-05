"""Tests for chunking strategies."""

import pytest

from core.shared.rag.chunking import Chunk, Chunker, ChunkStrategy
from core.shared.rag.exceptions import ChunkingError


SAMPLE_IT_TEXT = """Articolo 1 — Definizioni

Il presente regolamento disciplina la materia di cui all'oggetto.

Articolo 2 — Ambito di applicazione

Il regolamento si applica a tutti i soggetti operanti nel settore.
Sono esclusi i casi previsti dall'articolo 5.

Articolo 3 — Disposizioni generali

Le disposizioni del presente articolo prevalgono in caso di conflitto.
""" * 4  # ~1.6 kB, abbastanza per essere splittato


class TestChunkDataclass:
    def test_chunk_has_required_fields(self):
        c = Chunk(text="hello", metadata={"page": 1}, chunk_id="abc", sequence=0)
        assert c.text == "hello"
        assert c.metadata == {"page": 1}
        assert c.chunk_id == "abc"
        assert c.sequence == 0

    def test_chunk_id_generated_when_not_provided(self):
        c = Chunk.create(text="x", metadata={}, sequence=0)
        assert len(c.chunk_id) >= 16  # uuid4 hex
        assert c.text == "x"


class TestChunkStrategy:
    def test_strategy_enum_values(self):
        assert ChunkStrategy.SEMANTIC_AWARE.value == "semantic_aware"
        assert ChunkStrategy.FIXED_SIZE.value == "fixed_size"
        assert ChunkStrategy.STRUCTURAL.value == "structural"


class TestChunker:
    def test_default_strategy_is_semantic_aware(self):
        chunker = Chunker()
        assert chunker.strategy == ChunkStrategy.SEMANTIC_AWARE

    def test_semantic_chunker_produces_non_empty_chunks(self):
        chunker = Chunker(
            strategy=ChunkStrategy.SEMANTIC_AWARE, chunk_size=300, overlap=30
        )
        chunks = chunker.chunk_document(SAMPLE_IT_TEXT, metadata={"doc": "reg"})
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.text.strip() for c in chunks)

    def test_chunks_preserve_document_metadata(self):
        chunker = Chunker(chunk_size=200, overlap=20)
        chunks = chunker.chunk_document(SAMPLE_IT_TEXT, metadata={"doc_id": "X"})
        assert all(c.metadata.get("doc_id") == "X" for c in chunks)

    def test_chunks_have_sequential_ids(self):
        chunker = Chunker(chunk_size=200, overlap=20)
        chunks = chunker.chunk_document(SAMPLE_IT_TEXT, metadata={})
        seqs = [c.sequence for c in chunks]
        assert seqs == list(range(len(chunks)))

    def test_chunks_have_unique_chunk_ids(self):
        chunker = Chunker(chunk_size=200, overlap=20)
        chunks = chunker.chunk_document(SAMPLE_IT_TEXT, metadata={})
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_fixed_size_strategy_produces_fixed_size_chunks(self):
        chunker = Chunker(
            strategy=ChunkStrategy.FIXED_SIZE, chunk_size=200, overlap=0
        )
        chunks = chunker.chunk_document("a" * 1000, metadata={})
        for c in chunks[:-1]:
            assert len(c.text) == 200

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ChunkingError):
            Chunker(chunk_size=0)
        with pytest.raises(ChunkingError):
            Chunker(chunk_size=-5)

    def test_overlap_must_be_smaller_than_chunk_size(self):
        with pytest.raises(ChunkingError):
            Chunker(chunk_size=100, overlap=100)

    def test_empty_text_returns_empty_list(self):
        chunker = Chunker()
        assert chunker.chunk_document("", metadata={}) == []
        assert chunker.chunk_document("   \n  ", metadata={}) == []

    def test_structural_strategy_splits_on_sentence_markers(self):
        sentenza = (
            "Svolgimento del processo\n\n"
            "La parte attrice ha chiamato in giudizio.\n\n"
            "Motivi della decisione\n\n"
            "Il tribunale rileva che le risultanze documentali.\n\n"
            "Dispositivo\n\n"
            "Per questi motivi, il tribunale rigetta."
        )
        chunker = Chunker(strategy=ChunkStrategy.STRUCTURAL, chunk_size=2000)
        chunks = chunker.chunk_document(
            sentenza, metadata={"doc_type": "sentenza"}
        )
        sections = [c.metadata.get("section") for c in chunks]
        assert "Svolgimento del processo" in sections
        assert "Motivi della decisione" in sections
        assert "Dispositivo" in sections
