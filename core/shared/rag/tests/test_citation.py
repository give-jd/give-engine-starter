"""Tests for CitationParser + CitedResponse."""

from __future__ import annotations

import pytest

from core.shared.rag.chunking import Chunk
from core.shared.rag.citation import CitationParser, CitedResponse
from core.shared.rag.vector_store import ScoredChunk


def _make_scored_chunk(chunk_id: str, text: str, score: float = 0.9) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            text=text, metadata={"filename": "doc.pdf"},
            chunk_id=chunk_id, sequence=0,
        ),
        score=score,
        source="dense",
    )


@pytest.fixture
def parser() -> CitationParser:
    return CitationParser()


@pytest.fixture
def sample_chunks() -> list[ScoredChunk]:
    return [
        _make_scored_chunk("c1", "L'IVA si applica al 22% sulle fatture."),
        _make_scored_chunk("c2", "Il GDPR richiede consenso esplicito."),
        _make_scored_chunk("c3", "I bandi PNRR finanziano fino al 60%."),
    ]


class TestParseValid:
    def test_extracts_citation_labels(self, parser: CitationParser, sample_chunks):
        raw = "L'IVA è del 22% [chunk 1]. Il GDPR richiede consenso [chunk 2]."
        result = parser.parse(raw, sample_chunks)
        assert isinstance(result, CitedResponse)
        assert result.is_validated is True
        assert "chunk 1" in result.citations
        assert "chunk 2" in result.citations

    def test_citations_link_to_correct_chunks(self, parser, sample_chunks):
        raw = "Vedi [chunk 1] per IVA, e [chunk 3] per finanziamenti."
        result = parser.parse(raw, sample_chunks)
        assert result.citations["chunk 1"].chunk.chunk_id == "c1"
        assert result.citations["chunk 3"].chunk.chunk_id == "c3"

    def test_text_preserved(self, parser, sample_chunks):
        raw = "L'IVA è del 22% [chunk 1]. Punto."
        result = parser.parse(raw, sample_chunks)
        assert result.text == raw

    def test_multiple_citations_per_claim(self, parser, sample_chunks):
        raw = "Da [chunk 1] e [chunk 2] si evince che..."
        result = parser.parse(raw, sample_chunks)
        assert len(result.citations) == 2


class TestParseInvalid:
    def test_citation_to_nonexistent_chunk_marked_invalid(
        self, parser, sample_chunks
    ):
        raw = "Affermazione [chunk 99]."
        result = parser.parse(raw, sample_chunks)
        assert result.is_validated is False

    def test_no_citations_returns_not_validated(self, parser, sample_chunks):
        raw = "Affermazione senza fonti."
        result = parser.parse(raw, sample_chunks)
        assert result.citations == {}
        assert result.is_validated is False

    def test_empty_response_not_validated(self, parser, sample_chunks):
        result = parser.parse("", sample_chunks)
        assert result.is_validated is False


class TestRejectUncited:
    def test_reject_uncited_true_when_no_citations(self, parser, sample_chunks):
        raw = "Risposta senza fonti."
        result = parser.parse(raw, sample_chunks)
        assert parser.reject_uncited(result) is True

    def test_reject_uncited_false_when_valid(self, parser, sample_chunks):
        raw = "L'IVA è 22% [chunk 1]."
        result = parser.parse(raw, sample_chunks)
        assert parser.reject_uncited(result) is False

    def test_reject_uncited_true_when_invalid_citations_only(
        self, parser, sample_chunks
    ):
        raw = "Affermazione [chunk 99]."
        result = parser.parse(raw, sample_chunks)
        assert parser.reject_uncited(result) is True


class TestCitationFormats:
    def test_supports_chunk_N_with_space(self, parser, sample_chunks):
        raw = "Test [chunk 1]."
        result = parser.parse(raw, sample_chunks)
        assert "chunk 1" in result.citations

    def test_supports_chunk_N_with_underscore(self, parser, sample_chunks):
        raw = "Test [chunk_1]."
        result = parser.parse(raw, sample_chunks)
        assert "chunk 1" in result.citations

    def test_case_insensitive(self, parser, sample_chunks):
        raw = "Test [Chunk 1] e [CHUNK 2]."
        result = parser.parse(raw, sample_chunks)
        assert "chunk 1" in result.citations
        assert "chunk 2" in result.citations


class TestCitedResponseDataclass:
    def test_default_construction(self):
        r = CitedResponse(text="x", citations={}, is_validated=False)
        assert r.text == "x"
        assert r.citations == {}
        assert r.is_validated is False
