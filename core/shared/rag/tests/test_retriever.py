"""Tests for Retriever (semantic-only v0.1)."""

from pathlib import Path

import numpy as np
import pytest

from core.shared.rag.chunking import Chunk
from core.shared.rag.embedder import Embedder, EmbedderConfig
from core.shared.rag.exceptions import RetrievalError
from core.shared.rag.retriever import Retriever
from core.shared.rag.vector_store import ScoredChunk, VectorStore


DIM = 8


def _fake_encoder(texts: list[str], batch_size: int = 32) -> np.ndarray:
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        seed = sum(ord(c) for c in t) or 1
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(DIM).astype(np.float32)
        out[i] = v / np.linalg.norm(v)
    return out


@pytest.fixture
def populated_store(tmp_path: Path) -> VectorStore:
    store = VectorStore(db_path=tmp_path / "ret.db", dimension=DIM)
    chunks = [
        Chunk.create(text=f"contenuto {i}", metadata={"page": i}, sequence=i)
        for i in range(10)
    ]
    vectors = _fake_encoder([c.text for c in chunks])
    store.add_chunks(
        chunks=chunks,
        vectors=[vectors[i] for i in range(vectors.shape[0])],
        document_id="doc-1",
        filename="x.pdf",
        sha256="a" * 64,
    )
    return store


@pytest.fixture
def embedder() -> Embedder:
    cfg = EmbedderConfig(model_name="fake", device="cpu")
    return Embedder(cfg, encoder_fn=_fake_encoder, dimension=DIM)


class TestRetrieverInit:
    def test_default_flags_v0_1(self, populated_store: VectorStore, embedder: Embedder):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        assert r.enable_sparse is False
        assert r.enable_rerank is False

    def test_enabling_unsupported_features_is_noop(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(
            vector_store=populated_store,
            embedder=embedder,
            enable_sparse=True,
            enable_rerank=True,
        )
        assert r.enable_sparse is True
        assert r.enable_rerank is True


class TestRetrieve:
    def test_retrieve_returns_scored_chunks(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        results = r.retrieve("contenuto 0", top_k=3, min_score=0.0)
        assert len(results) == 3
        assert all(isinstance(x, ScoredChunk) for x in results)

    def test_retrieve_respects_min_score(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        results_loose = r.retrieve("contenuto 0", top_k=10, min_score=0.0)
        results_strict = r.retrieve("contenuto 0", top_k=10, min_score=0.99)
        assert len(results_loose) >= len(results_strict)
        for sc in results_strict:
            assert sc.score >= 0.99

    def test_retrieve_results_sorted_descending_by_score(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        results = r.retrieve("contenuto 0", top_k=10, min_score=0.0)
        scores = [sc.score for sc in results]
        assert scores == sorted(scores, reverse=True)

    def test_retrieve_top_k_caps_results(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        results = r.retrieve("contenuto 0", top_k=2, min_score=0.0)
        assert len(results) <= 2

    def test_empty_query_raises(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        with pytest.raises(RetrievalError):
            r.retrieve("", top_k=5)
        with pytest.raises(RetrievalError):
            r.retrieve("   ", top_k=5)

    def test_invalid_top_k_raises(
        self, populated_store: VectorStore, embedder: Embedder
    ):
        r = Retriever(vector_store=populated_store, embedder=embedder)
        with pytest.raises(RetrievalError):
            r.retrieve("x", top_k=0)
        with pytest.raises(RetrievalError):
            r.retrieve("x", top_k=-1)

    def test_retrieve_on_empty_store_returns_empty(self, tmp_path: Path, embedder: Embedder):
        empty = VectorStore(db_path=tmp_path / "empty.db", dimension=DIM)
        r = Retriever(vector_store=empty, embedder=embedder)
        results = r.retrieve("anything", top_k=5, min_score=0.0)
        assert results == []
