"""Tests for VectorStore (sqlite-vec wrapper)."""

from pathlib import Path

import numpy as np
import pytest

from core.shared.rag.chunking import Chunk
from core.shared.rag.exceptions import VectorStoreError
from core.shared.rag.vector_store import VectorStore


DIM = 8  # tiny dimension for fast tests


def _fake_vector(seed: int, dim: int = DIM) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _make_chunks(n: int, doc_id: str = "doc-1") -> list[Chunk]:
    return [
        Chunk.create(
            text=f"chunk {i} of {doc_id}",
            metadata={"doc_id": doc_id, "page": i + 1},
            sequence=i,
        )
        for i in range(n)
    ]


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    db = tmp_path / "test.db"
    return VectorStore(db_path=db, dimension=DIM)


class TestVectorStoreInit:
    def test_creates_db_file(self, tmp_path: Path):
        db = tmp_path / "new.db"
        assert not db.exists()
        VectorStore(db_path=db, dimension=DIM)
        assert db.exists()

    def test_dimension_mismatch_raises(self, tmp_path: Path):
        db = tmp_path / "x.db"
        VectorStore(db_path=db, dimension=DIM)
        with pytest.raises(VectorStoreError) as excinfo:
            VectorStore(db_path=db, dimension=DIM + 1)
        assert excinfo.value.expected == DIM
        assert excinfo.value.actual == DIM + 1


class TestAddAndSearch:
    def test_add_chunks_then_search_returns_results(self, store: VectorStore):
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        store.add_chunks(
            chunks=chunks,
            vectors=vectors,
            document_id="doc-1",
            filename="reg.pdf",
            sha256="a" * 64,
        )
        results = store.search(query_vector=_fake_vector(0), top_k=2)
        assert len(results) == 2
        assert results[0].chunk.chunk_id == chunks[0].chunk_id

    def test_search_returns_scored_chunks_with_metadata(self, store: VectorStore):
        chunks = _make_chunks(2)
        vectors = [_fake_vector(i) for i in range(2)]
        store.add_chunks(
            chunks=chunks,
            vectors=vectors,
            document_id="doc-1",
            filename="reg.pdf",
            sha256="b" * 64,
        )
        results = store.search(query_vector=_fake_vector(0), top_k=1)
        assert results[0].chunk.metadata["doc_id"] == "doc-1"
        assert results[0].chunk.metadata["page"] == 1
        assert 0.0 <= results[0].score <= 1.0

    def test_search_respects_top_k(self, store: VectorStore):
        chunks = _make_chunks(5)
        vectors = [_fake_vector(i) for i in range(5)]
        store.add_chunks(
            chunks=chunks,
            vectors=vectors,
            document_id="doc-1",
            filename="x.pdf",
            sha256="c" * 64,
        )
        assert len(store.search(_fake_vector(0), top_k=3)) == 3
        assert len(store.search(_fake_vector(0), top_k=10)) == 5

    def test_add_chunks_with_wrong_vector_dim_raises(self, store: VectorStore):
        chunks = _make_chunks(1)
        bad_vector = np.zeros(DIM + 2, dtype=np.float32)
        with pytest.raises(VectorStoreError):
            store.add_chunks(
                chunks=chunks,
                vectors=[bad_vector],
                document_id="doc-1",
                filename="x.pdf",
                sha256="d" * 64,
            )

    def test_add_chunks_length_mismatch_raises(self, store: VectorStore):
        chunks = _make_chunks(2)
        vectors = [_fake_vector(0)]
        with pytest.raises(VectorStoreError):
            store.add_chunks(
                chunks=chunks,
                vectors=vectors,
                document_id="doc-1",
                filename="x.pdf",
                sha256="e" * 64,
            )


class TestDeleteAndStats:
    def test_delete_document_removes_chunks_and_vectors(self, store: VectorStore):
        chunks = _make_chunks(3)
        vectors = [_fake_vector(i) for i in range(3)]
        store.add_chunks(
            chunks=chunks,
            vectors=vectors,
            document_id="doc-x",
            filename="x.pdf",
            sha256="f" * 64,
        )
        assert store.stats()["total_chunks"] == 3
        store.delete_document("doc-x")
        assert store.stats()["total_chunks"] == 0
        assert store.stats()["total_documents"] == 0
        assert store.search(_fake_vector(0), top_k=5) == []

    def test_stats_reflects_state(self, store: VectorStore):
        s0 = store.stats()
        assert s0["total_chunks"] == 0
        assert s0["total_documents"] == 0

        store.add_chunks(
            chunks=_make_chunks(2, doc_id="doc-a"),
            vectors=[_fake_vector(i) for i in range(2)],
            document_id="doc-a",
            filename="a.pdf",
            sha256="1" * 64,
        )
        store.add_chunks(
            chunks=_make_chunks(3, doc_id="doc-b"),
            vectors=[_fake_vector(i + 10) for i in range(3)],
            document_id="doc-b",
            filename="b.pdf",
            sha256="2" * 64,
        )
        s = store.stats()
        assert s["total_chunks"] == 5
        assert s["total_documents"] == 2

    def test_duplicate_sha256_is_rejected(self, store: VectorStore):
        store.add_chunks(
            chunks=_make_chunks(1, doc_id="doc-a"),
            vectors=[_fake_vector(0)],
            document_id="doc-a",
            filename="a.pdf",
            sha256="9" * 64,
        )
        with pytest.raises(VectorStoreError):
            store.add_chunks(
                chunks=_make_chunks(1, doc_id="doc-b"),
                vectors=[_fake_vector(1)],
                document_id="doc-b",
                filename="b.pdf",
                sha256="9" * 64,
            )


class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path: Path):
        db = tmp_path / "persist.db"
        s1 = VectorStore(db_path=db, dimension=DIM)
        s1.add_chunks(
            chunks=_make_chunks(2),
            vectors=[_fake_vector(i) for i in range(2)],
            document_id="doc-1",
            filename="x.pdf",
            sha256="7" * 64,
        )
        s1.close()

        s2 = VectorStore(db_path=db, dimension=DIM)
        assert s2.stats()["total_chunks"] == 2
        results = s2.search(_fake_vector(0), top_k=1)
        assert len(results) == 1
