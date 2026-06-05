"""Retriever: orchestrates embedding + vector store search.

v0.1 implements dense retrieval only. The `enable_sparse` and
`enable_rerank` flags are accepted to keep the v0.1 API forward-compatible
with v0.4, but they are no-ops for now and emit a warning when set.
"""

from __future__ import annotations

import logging

from core.shared.rag.embedder import Embedder
from core.shared.rag.exceptions import RetrievalError
from core.shared.rag.vector_store import ScoredChunk, VectorStore


_log = logging.getLogger(__name__)


class Retriever:
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder,
        enable_sparse: bool = False,
        enable_rerank: bool = False,
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder
        self.enable_sparse = enable_sparse
        self.enable_rerank = enable_rerank
        if enable_sparse:
            _log.warning(
                "enable_sparse=True ignored: hybrid BM25 lands in rag v0.4"
            )
        if enable_rerank:
            _log.warning(
                "enable_rerank=True ignored: cross-encoder rerank lands in rag v0.4"
            )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5,
        filters: dict | None = None,
    ) -> list[ScoredChunk]:
        if not query or not query.strip():
            raise RetrievalError("query must be non-empty")
        if top_k <= 0:
            raise RetrievalError(f"top_k must be > 0, got {top_k}")

        query_vector = self.embedder.embed_query(query)
        scored = self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filters=filters,
        )
        scored = [sc for sc in scored if sc.score >= min_score]
        scored.sort(key=lambda sc: sc.score, reverse=True)
        return scored[:top_k]
