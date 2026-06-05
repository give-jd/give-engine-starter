"""Tests BM25 + Hybrid retrieval v0.5.0."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.shared.rag.bm25 import STOP_WORDS_IT, BM25Index
from core.shared.rag.hybrid import HybridRetriever


@dataclass(frozen=True)
class FakeHit:
    chunk_id: str
    score: float


CORPUS = [
    ("c1", "art 6 GDPR base giuridica liceita trattamento"),
    ("c2", "art 9 GDPR categorie dati particolari sanitari"),
    ("c3", "art 30 GDPR registro trattamenti titolare"),
    ("c4", "art 32 GDPR misure sicurezza adeguate"),
    ("c5", "art 5 GDPR principi liceita correttezza"),
    ("c6", "trasferimenti extra UE clausole standard SCC"),
]


@pytest.fixture
def bm25_built():
    idx = BM25Index()
    for cid, text in CORPUS:
        idx.add_chunk(cid, text)
    idx.build()
    return idx


class TestStopWords:
    def test_it_contains_common(self):
        for w in ("il", "la", "di", "che", "non", "e"):
            assert w in STOP_WORDS_IT

    def test_it_excludes_content_words(self):
        for w in ("gdpr", "trattamento", "categorie"):
            assert w not in STOP_WORDS_IT


class TestTokenize:
    def test_lowercase(self):
        idx = BM25Index()
        assert "gdpr" in idx.tokenize("GDPR Articolo")

    def test_filtra_stop_word(self):
        idx = BM25Index()
        tokens = idx.tokenize("il trattamento e' la base")
        assert "il" not in tokens
        assert "trattamento" in tokens
        assert "base" in tokens

    def test_filtra_unicarattere(self):
        idx = BM25Index()
        tokens = idx.tokenize("art a b ad")
        assert "a" not in tokens
        assert "b" not in tokens

    def test_punteggiatura_split(self):
        idx = BM25Index()
        tokens = idx.tokenize("art. 472, GDPR — base!")
        assert "art" in tokens
        assert "472" in tokens
        assert "gdpr" in tokens
        assert "base" in tokens


class TestBM25Index:
    def test_add_chunk(self):
        idx = BM25Index()
        idx.add_chunk("c1", "art 6 GDPR")
        assert idx.n_docs() == 1

    def test_duplicato_rifiutato(self):
        idx = BM25Index()
        idx.add_chunk("c1", "x")
        with pytest.raises(ValueError, match="duplicato"):
            idx.add_chunk("c1", "y")

    def test_add_dopo_build_rifiutato(self, bm25_built):
        with pytest.raises(RuntimeError, match="build"):
            bm25_built.add_chunk("cN", "nuovo")

    def test_search_senza_build_rifiutato(self):
        idx = BM25Index()
        idx.add_chunk("c1", "x")
        with pytest.raises(RuntimeError, match="build"):
            idx.search("x")

    def test_search_corpus_vuoto(self):
        idx = BM25Index()
        idx.build()
        assert idx.search("query") == []

    def test_search_k_invalido(self, bm25_built):
        with pytest.raises(ValueError, match="k"):
            bm25_built.search("art", k=0)

    def test_search_query_solo_stop_words(self, bm25_built):
        results = bm25_built.search("il che la")
        assert results == []

    def test_search_term_specifico(self, bm25_built):
        results = bm25_built.search("sanitari")
        assert len(results) >= 1
        assert results[0].chunk_id == "c2"

    def test_search_multipli_termini(self, bm25_built):
        results = bm25_built.search("art 9 categorie")
        cids = [r.chunk_id for r in results]
        assert "c2" in cids
        assert cids.index("c2") == 0

    def test_search_k_limit(self, bm25_built):
        results = bm25_built.search("art", k=3)
        assert len(results) <= 3

    def test_search_scores_decrescenti(self, bm25_built):
        results = bm25_built.search("GDPR art")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_n_terms_dopo_build(self, bm25_built):
        assert bm25_built.n_terms() > 0


class TestBM25Parametri:
    def test_k1_custom(self):
        idx = BM25Index(k1=2.0)
        idx.add_chunk("c1", "art art art GDPR")
        idx.build()
        results = idx.search("art")
        assert len(results) == 1

    def test_b_custom(self):
        idx = BM25Index(b=0.0)
        idx.add_chunk("c1", "art")
        idx.add_chunk("c2", "art GDPR norma trattamento liceita")
        idx.build()
        r = idx.search("art")
        scores = {h.chunk_id: h.score for h in r}
        assert abs(scores["c1"] - scores["c2"]) < 0.01

    def test_stop_words_custom(self):
        idx = BM25Index(stop_words=frozenset({"foo"}))
        tokens = idx.tokenize("foo bar baz")
        assert "foo" not in tokens
        assert "bar" in tokens


def make_dense_fn(hits: list[FakeHit]):
    def fn(query: str, k: int):
        return hits[:k]
    return fn


def make_sparse_fn(hits: list[FakeHit]):
    def fn(query: str, k: int):
        return hits[:k]
    return fn


class TestHybridRRF:
    def test_overlap_boost(self):
        dense = [FakeHit("c1", 0.95), FakeHit("c3", 0.85)]
        sparse = [FakeHit("c1", 5.0), FakeHit("c2", 4.0)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn(sparse),
        )
        result = hr.search("q", k=5, strategy="rrf")
        assert result.strategy == "rrf"
        assert result.n_overlap == 1
        assert result.hits[0].chunk_id == "c1"

    def test_solo_dense(self):
        dense = [FakeHit("c1", 0.9), FakeHit("c2", 0.8)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn([]),
        )
        r = hr.search("q", k=5)
        assert len(r.hits) == 2
        assert r.n_overlap == 0

    def test_solo_sparse(self):
        sparse = [FakeHit("c5", 3.0), FakeHit("c6", 2.0)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn([]),
            sparse_fn=make_sparse_fn(sparse),
        )
        r = hr.search("q", k=5)
        assert len(r.hits) == 2

    def test_k_limita(self):
        dense = [FakeHit(f"c{i}", 1.0/i) for i in range(1, 11)]
        sparse = [FakeHit(f"d{i}", 1.0/i) for i in range(1, 11)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn(sparse),
        )
        r = hr.search("q", k=5)
        assert len(r.hits) == 5

    def test_hybrid_hit_metadata(self):
        dense = [FakeHit("c1", 0.9)]
        sparse = [FakeHit("c1", 3.0)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn(sparse),
        )
        r = hr.search("q", k=5)
        h = r.hits[0]
        assert h.dense_rank == 1
        assert h.sparse_rank == 1
        assert h.dense_score == pytest.approx(0.9)
        assert h.sparse_score == pytest.approx(3.0)


class TestHybridWeighted:
    def test_weighted_dense_pesato_maggiore(self):
        dense = [FakeHit("c1", 1.0)]
        sparse = [FakeHit("c2", 1.0)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn(sparse),
            weight_dense=0.9, weight_sparse=0.1,
        )
        r = hr.search("q", k=5, strategy="weighted")
        assert r.hits[0].chunk_id == "c1"

    def test_weighted_sparse_pesato_maggiore(self):
        dense = [FakeHit("c1", 1.0)]
        sparse = [FakeHit("c2", 1.0)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn(sparse),
            weight_dense=0.1, weight_sparse=0.9,
        )
        r = hr.search("q", k=5, strategy="weighted")
        assert r.hits[0].chunk_id == "c2"


class TestHybridWaterfall:
    def test_dense_sufficiente(self):
        dense = [FakeHit("c1", 1.0), FakeHit("c2", 0.9), FakeHit("c3", 0.8)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn([FakeHit("c99", 99.0)]),
            waterfall_min_dense=3,
        )
        r = hr.search("q", k=3, strategy="waterfall")
        assert r.n_sparse == 0
        cids = [h.chunk_id for h in r.hits]
        assert "c99" not in cids

    def test_dense_insufficiente_fallback_sparse(self):
        dense = [FakeHit("c1", 1.0)]
        sparse = [FakeHit("c2", 0.5), FakeHit("c3", 0.4)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(dense),
            sparse_fn=make_sparse_fn(sparse),
            waterfall_min_dense=3,
        )
        r = hr.search("q", k=5, strategy="waterfall")
        assert r.n_sparse == 2
        cids = [h.chunk_id for h in r.hits]
        assert "c1" in cids
        assert "c2" in cids


class TestHybridErrori:
    def test_strategy_invalida(self):
        hr = HybridRetriever(
            dense_fn=make_dense_fn([]),
            sparse_fn=make_sparse_fn([]),
        )
        with pytest.raises(ValueError, match="strategy"):
            hr.search("q", strategy="random-xyz")

    def test_k_zero(self):
        hr = HybridRetriever(
            dense_fn=make_dense_fn([]),
            sparse_fn=make_sparse_fn([]),
        )
        with pytest.raises(ValueError, match="k"):
            hr.search("q", k=0)


class TestIntegrationBM25Hybrid:
    def test_bm25_in_hybrid(self, bm25_built):
        def bm25_adapter(query, k):
            return [
                FakeHit(h.chunk_id, h.score)
                for h in bm25_built.search(query, k=k)
            ]
        fake_dense = [FakeHit("c1", 0.95), FakeHit("c5", 0.85)]
        hr = HybridRetriever(
            dense_fn=make_dense_fn(fake_dense),
            sparse_fn=bm25_adapter,
        )
        r = hr.search("art 9 sanitari", k=5, strategy="rrf")
        cids = [h.chunk_id for h in r.hits]
        assert "c2" in cids
