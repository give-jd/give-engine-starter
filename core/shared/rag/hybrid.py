"""Hybrid retrieval v0.5.0 — combina dense (embeddings) + sparse (BM25).

Strategie fusion:
- RRF (Reciprocal Rank Fusion, Cormack/Clarke/Buettcher 2009): no normalization,
  robusto a score scales diverse. Default.
- weighted: combinazione lineare con normalizzazione min-max per ranking.
- waterfall: dense primary, sparse fallback se dense recall basso.

Pattern:
    retriever = HybridRetriever(dense_fn=base.retrieve, bm25_index=idx)
    result = retriever.search("query complessa", k=10, strategy="rrf")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class HybridHit:
    chunk_id: str
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None


class HasChunkId(Protocol):
    chunk_id: str
    score: float


@dataclass
class HybridResult:
    hits: list[HybridHit]
    strategy: str
    n_dense: int = 0
    n_sparse: int = 0
    n_overlap: int = 0


DenseRetriever = Callable[[str, int], list[HasChunkId]]
SparseRetriever = Callable[[str, int], list[HasChunkId]]


@dataclass
class HybridRetriever:
    dense_fn: DenseRetriever
    sparse_fn: SparseRetriever
    rrf_k: int = 60
    weight_dense: float = 0.6
    weight_sparse: float = 0.4
    waterfall_min_dense: int = 3

    def search(self, query: str, k: int = 10,
              strategy: str = "rrf",
              k_each: int | None = None) -> HybridResult:
        if k < 1:
            raise ValueError("k deve essere >= 1")
        if k_each is None:
            k_each = max(k * 2, 10)

        if strategy == "rrf":
            return self._rrf(query, k, k_each)
        if strategy == "weighted":
            return self._weighted(query, k, k_each)
        if strategy == "waterfall":
            return self._waterfall(query, k, k_each)
        raise ValueError(f"strategy non riconosciuta: {strategy}")

    def _rrf(self, query: str, k: int, k_each: int) -> HybridResult:
        dense = list(self.dense_fn(query, k_each))
        sparse = list(self.sparse_fn(query, k_each))

        rrf_scores: dict[str, float] = {}
        dense_ranks: dict[str, int] = {}
        sparse_ranks: dict[str, int] = {}
        dense_scores: dict[str, float] = {}
        sparse_scores: dict[str, float] = {}

        for rank, hit in enumerate(dense, start=1):
            cid = hit.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (self.rrf_k + rank)
            dense_ranks[cid] = rank
            dense_scores[cid] = float(hit.score)

        for rank, hit in enumerate(sparse, start=1):
            cid = hit.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (self.rrf_k + rank)
            sparse_ranks[cid] = rank
            sparse_scores[cid] = float(hit.score)

        overlap = set(dense_ranks) & set(sparse_ranks)
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        hits = [
            HybridHit(
                chunk_id=cid,
                score=s,
                dense_rank=dense_ranks.get(cid),
                sparse_rank=sparse_ranks.get(cid),
                dense_score=dense_scores.get(cid),
                sparse_score=sparse_scores.get(cid),
            )
            for cid, s in ranked[:k]
        ]
        return HybridResult(
            hits=hits,
            strategy="rrf",
            n_dense=len(dense),
            n_sparse=len(sparse),
            n_overlap=len(overlap),
        )

    def _weighted(self, query: str, k: int, k_each: int) -> HybridResult:
        dense = list(self.dense_fn(query, k_each))
        sparse = list(self.sparse_fn(query, k_each))

        dense_norm = _minmax_norm({h.chunk_id: float(h.score) for h in dense})
        sparse_norm = _minmax_norm({h.chunk_id: float(h.score) for h in sparse})

        combined: dict[str, float] = {}
        for cid, sn in dense_norm.items():
            combined[cid] = combined.get(cid, 0.0) + self.weight_dense * sn
        for cid, sn in sparse_norm.items():
            combined[cid] = combined.get(cid, 0.0) + self.weight_sparse * sn

        dense_ranks = {h.chunk_id: i + 1 for i, h in enumerate(dense)}
        sparse_ranks = {h.chunk_id: i + 1 for i, h in enumerate(sparse)}
        dense_raw = {h.chunk_id: float(h.score) for h in dense}
        sparse_raw = {h.chunk_id: float(h.score) for h in sparse}

        overlap = set(dense_ranks) & set(sparse_ranks)
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        hits = [
            HybridHit(
                chunk_id=cid,
                score=s,
                dense_rank=dense_ranks.get(cid),
                sparse_rank=sparse_ranks.get(cid),
                dense_score=dense_raw.get(cid),
                sparse_score=sparse_raw.get(cid),
            )
            for cid, s in ranked[:k]
        ]
        return HybridResult(
            hits=hits,
            strategy="weighted",
            n_dense=len(dense),
            n_sparse=len(sparse),
            n_overlap=len(overlap),
        )

    def _waterfall(self, query: str, k: int, k_each: int) -> HybridResult:
        dense = list(self.dense_fn(query, k_each))
        n_dense = len(dense)

        if n_dense >= self.waterfall_min_dense:
            hits = [
                HybridHit(
                    chunk_id=h.chunk_id,
                    score=float(h.score),
                    dense_rank=i + 1,
                    dense_score=float(h.score),
                )
                for i, h in enumerate(dense[:k])
            ]
            return HybridResult(hits=hits, strategy="waterfall",
                                n_dense=n_dense, n_sparse=0, n_overlap=0)

        sparse = list(self.sparse_fn(query, k_each))
        dense_ids = {h.chunk_id for h in dense}
        merged_hits: list[HybridHit] = []
        for i, h in enumerate(dense):
            merged_hits.append(HybridHit(
                chunk_id=h.chunk_id, score=float(h.score),
                dense_rank=i + 1, dense_score=float(h.score),
            ))
        for i, h in enumerate(sparse):
            if h.chunk_id in dense_ids:
                continue
            merged_hits.append(HybridHit(
                chunk_id=h.chunk_id, score=float(h.score),
                sparse_rank=i + 1, sparse_score=float(h.score),
            ))
        return HybridResult(
            hits=merged_hits[:k],
            strategy="waterfall",
            n_dense=n_dense,
            n_sparse=len(sparse),
            n_overlap=0,
        )


def _minmax_norm(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}
