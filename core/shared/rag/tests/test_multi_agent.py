"""Tests multi-agent retrieval v0.4.0."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.shared.rag.exceptions import RetrievalError
from core.shared.rag.multi_agent import (
    MultiAgentRetriever,
    default_subquery_generator,
)


@dataclass
class FakeChunk:
    chunk_id: str
    text: str


@dataclass
class FakeScored:
    chunk: FakeChunk
    score: float
    source: str = "dense"


class FakeRetriever:
    def __init__(self, dataset: dict[str, list[FakeScored]]):
        self.dataset = dataset
        self.calls: list[str] = []

    def retrieve(self, query: str, k: int = 5) -> list[FakeScored]:
        self.calls.append(query)
        results = self.dataset.get(query, [])
        return list(results[:k])


@pytest.fixture
def retriever():
    c1 = FakeScored(FakeChunk("c1", "art. 6 GDPR base giuridica liceita"), 0.95)
    c2 = FakeScored(FakeChunk("c2", "art. 9 GDPR categorie dati particolari sanitari"), 0.92)
    c3 = FakeScored(FakeChunk("c3", "art. 30 GDPR registro trattamenti"), 0.88)
    c4 = FakeScored(FakeChunk("c4", "art. 32 GDPR misure sicurezza adeguate"), 0.85)
    c5 = FakeScored(FakeChunk("c5", "art. 5 GDPR principi liceita correttezza"), 0.80)
    c6 = FakeScored(FakeChunk("c6", "trasferimenti extra UE clausole standard SCC"), 0.78)
    return FakeRetriever({
        "art 6 GDPR": [c1, c5],
        "art 9 GDPR": [c2, c3],
        "registro trattamenti": [c3, c1],
        "art 6 GDPR e art 9 GDPR": [c1, c2, c3],
        "GDPR art 6 art 9 base giuridica": [c1, c2, c5, c3],
        "registro": [c3],
        "trasferimenti UE": [c6, c4],
        "complete query": [c1, c2, c3, c4, c5, c6],
    })


class TestDefaultSubqueryGenerator:
    def test_punteggiatura(self):
        out = default_subquery_generator("art. 6 GDPR. art. 9 GDPR.", 5)
        assert len(out) == 2

    def test_split_e(self):
        out = default_subquery_generator("art 6 GDPR e art 9 GDPR", 3)
        assert "art 6 GDPR" in out
        assert "art 9 GDPR" in out

    def test_max_subqueries_limit(self):
        out = default_subquery_generator(
            "alpha e beta e gamma e delta e epsilon", 2)
        assert len(out) == 2

    def test_query_singola(self):
        out = default_subquery_generator("query semplice", 3)
        assert out == ["query semplice"]

    def test_clausola_corta_filtrata(self):
        out = default_subquery_generator("ab e art 9 GDPR", 5)
        assert "ab" not in out

    def test_dedup_case_insensitive(self):
        out = default_subquery_generator("GDPR e gdpr e GDPR", 5)
        assert len(out) == 1


class TestDecomposeRetrieve:
    def test_decompose_basic(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.decompose_retrieve("art 6 GDPR e art 9 GDPR", max_subqueries=2, k_per_subquery=2)
        assert r.strategy == "decompose"
        assert len(r.sub_queries) == 2
        ids = [c.chunk.chunk_id for c in r.chunks]
        assert "c1" in ids
        assert "c2" in ids

    def test_dedup_chunks(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.decompose_retrieve("art 6 GDPR e registro trattamenti", max_subqueries=2, k_per_subquery=3)
        ids = [c.chunk.chunk_id for c in r.chunks]
        assert ids.count("c1") == 1

    def test_sort_by_score(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.decompose_retrieve("art 6 GDPR e art 9 GDPR", max_subqueries=2, k_per_subquery=3)
        scores = [c.score for c in r.chunks]
        assert scores == sorted(scores, reverse=True)

    def test_max_subqueries_zero_invalid(self, retriever):
        agent = MultiAgentRetriever(retriever)
        with pytest.raises(RetrievalError, match="max_subqueries"):
            agent.decompose_retrieve("q", max_subqueries=0)

    def test_k_per_subquery_zero_invalid(self, retriever):
        agent = MultiAgentRetriever(retriever)
        with pytest.raises(RetrievalError, match="k_per_subquery"):
            agent.decompose_retrieve("q", k_per_subquery=0)

    def test_custom_subquery_generator(self, retriever):
        def custom(q, n):
            return ["art 6 GDPR", "art 9 GDPR"]

        agent = MultiAgentRetriever(retriever, subquery_generator=custom)
        r = agent.decompose_retrieve("qualsiasi cosa", max_subqueries=2, k_per_subquery=1)
        assert r.sub_queries == ["art 6 GDPR", "art 9 GDPR"]


class TestEnsembleRetrieve:
    def test_ensemble_basic(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.ensemble_retrieve("complete query", k=3, n_passes=2)
        assert r.strategy == "ensemble"
        assert r.n_passes == 2
        assert len(r.chunks) <= 3

    def test_ensemble_dedup(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.ensemble_retrieve("art 6 GDPR", k=10, n_passes=3)
        ids = [c.chunk.chunk_id for c in r.chunks]
        assert len(ids) == len(set(ids))

    def test_n_passes_zero_invalid(self, retriever):
        agent = MultiAgentRetriever(retriever)
        with pytest.raises(RetrievalError, match="n_passes"):
            agent.ensemble_retrieve("q", n_passes=0)

    def test_k_zero_invalid(self, retriever):
        agent = MultiAgentRetriever(retriever)
        with pytest.raises(RetrievalError, match="k"):
            agent.ensemble_retrieve("q", k=0)

    def test_ensemble_chiamate_multiple(self, retriever):
        agent = MultiAgentRetriever(retriever)
        agent.ensemble_retrieve("art 6 GDPR", k=5, n_passes=3)
        assert retriever.calls.count("art 6 GDPR") == 3


class TestRecursiveRetrieve:
    def test_recursive_basic(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.recursive_retrieve("art 6 GDPR", depth=1, k_per_depth=2)
        assert r.strategy == "recursive"
        assert r.iterations >= 1

    def test_depth_zero_invalid(self, retriever):
        agent = MultiAgentRetriever(retriever)
        with pytest.raises(RetrievalError, match="depth"):
            agent.recursive_retrieve("q", depth=0)

    def test_k_per_depth_zero_invalid(self, retriever):
        agent = MultiAgentRetriever(retriever)
        with pytest.raises(RetrievalError, match="k_per_depth"):
            agent.recursive_retrieve("q", k_per_depth=0)

    def test_recursive_stop_se_no_nuovi(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.recursive_retrieve("art 6 GDPR", depth=3, k_per_depth=10)
        assert r.iterations <= 3


class TestMultiAgentResultStructure:
    def test_decompose_fields(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.decompose_retrieve("art 6 GDPR e art 9 GDPR")
        assert r.strategy == "decompose"
        assert isinstance(r.sub_queries, list)
        assert r.n_passes == 1
        assert r.iterations == 1

    def test_ensemble_fields(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.ensemble_retrieve("art 6 GDPR", k=3, n_passes=2)
        assert r.strategy == "ensemble"
        assert r.n_passes == 2

    def test_recursive_fields(self, retriever):
        agent = MultiAgentRetriever(retriever)
        r = agent.recursive_retrieve("art 6 GDPR", depth=1)
        assert r.strategy == "recursive"
        assert r.iterations >= 1
