"""Multi-agent retrieval v0.4.0.

Orchestra multiple retrieval queries per migliorare recall su query complesse.

Pattern supportati:
- decompose: query complessa -> N sub-queries (intent classification)
- ensemble: stessa query -> N retrievers/embeddings -> union deduplicata
- recursive: query iniziale -> top-k chunks -> nuova query dai chunks -> iterate

Tipico uso (decompose):
    agent = MultiAgentRetriever(retriever=base_retriever)
    chunks = agent.decompose_retrieve(query, max_subqueries=3, k_per_subquery=3)

Tipico uso (ensemble con multi-pass embeddings):
    chunks = agent.ensemble_retrieve(query, k=10, n_passes=3)

Tipico uso (recursive):
    chunks = agent.recursive_retrieve(query, depth=2, k_per_depth=5)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List

from core.shared.rag.exceptions import RetrievalError
from core.shared.rag.retriever import Retriever
from core.shared.rag.vector_store import ScoredChunk


@dataclass
class MultiAgentResult:
    chunks: list[ScoredChunk]
    strategy: str
    sub_queries: list[str] = field(default_factory=list)
    n_passes: int = 1
    iterations: int = 1


SubqueryGenerator = Callable[[str, int], List[str]]


def default_subquery_generator(query: str, max_subqueries: int) -> list[str]:
    parts: list[str] = []

    sentences = re.split(r"[.;?!]\s+", query.strip())
    for s in sentences:
        s = s.strip().rstrip("?.")
        if not s:
            continue
        for clause in re.split(r"\s+(?:e\s|ed\s|ma\s|oppure\s|o\s|inoltre\s|nonche\s)", s, flags=re.I):
            clause = clause.strip()
            if clause and len(clause) > 3 and clause.lower() not in {p.lower() for p in parts}:
                parts.append(clause)
                if len(parts) >= max_subqueries:
                    return parts

    if not parts:
        parts.append(query.strip())
    return parts[:max_subqueries]


class MultiAgentRetriever:
    def __init__(
        self,
        retriever: Retriever,
        subquery_generator: SubqueryGenerator | None = None,
    ) -> None:
        self.retriever = retriever
        self.subquery_generator = subquery_generator or default_subquery_generator

    def decompose_retrieve(
        self,
        query: str,
        max_subqueries: int = 3,
        k_per_subquery: int = 3,
    ) -> MultiAgentResult:
        if max_subqueries < 1:
            raise RetrievalError("max_subqueries deve essere >= 1")
        if k_per_subquery < 1:
            raise RetrievalError("k_per_subquery deve essere >= 1")

        sub_queries = self.subquery_generator(query, max_subqueries)
        if not sub_queries:
            sub_queries = [query]

        seen_ids: set[str] = set()
        merged: list[ScoredChunk] = []
        for sq in sub_queries:
            chunks = self.retriever.retrieve(sq, k=k_per_subquery)
            for c in chunks:
                key = _chunk_key(c)
                if key not in seen_ids:
                    seen_ids.add(key)
                    merged.append(c)

        merged.sort(key=lambda c: c.score, reverse=True)
        return MultiAgentResult(
            chunks=merged,
            strategy="decompose",
            sub_queries=sub_queries,
        )

    def ensemble_retrieve(
        self,
        query: str,
        k: int = 10,
        n_passes: int = 3,
    ) -> MultiAgentResult:
        if n_passes < 1:
            raise RetrievalError("n_passes deve essere >= 1")
        if k < 1:
            raise RetrievalError("k deve essere >= 1")

        seen_ids: set[str] = set()
        ensemble_chunks: dict[str, ScoredChunk] = {}

        for _ in range(n_passes):
            chunks = self.retriever.retrieve(query, k=k)
            for c in chunks:
                key = _chunk_key(c)
                if key not in seen_ids:
                    seen_ids.add(key)
                    ensemble_chunks[key] = c
                else:
                    prev = ensemble_chunks[key]
                    prev.score = max(prev.score, c.score)

        ranked = sorted(ensemble_chunks.values(), key=lambda c: c.score, reverse=True)
        return MultiAgentResult(
            chunks=ranked[:k],
            strategy="ensemble",
            n_passes=n_passes,
        )

    def recursive_retrieve(
        self,
        query: str,
        depth: int = 2,
        k_per_depth: int = 5,
    ) -> MultiAgentResult:
        if depth < 1:
            raise RetrievalError("depth deve essere >= 1")
        if k_per_depth < 1:
            raise RetrievalError("k_per_depth deve essere >= 1")

        seen_ids: set[str] = set()
        all_chunks: list[ScoredChunk] = []
        current_query = query
        iteration = 0

        for iteration in range(depth):
            chunks = self.retriever.retrieve(current_query, k=k_per_depth)
            new_chunks: list[ScoredChunk] = []
            for c in chunks:
                key = _chunk_key(c)
                if key not in seen_ids:
                    seen_ids.add(key)
                    new_chunks.append(c)
                    all_chunks.append(c)

            if not new_chunks or iteration == depth - 1:
                break

            keywords = _extract_keywords(new_chunks[:3])
            current_query = f"{query} {keywords}".strip()

        all_chunks.sort(key=lambda c: c.score, reverse=True)
        return MultiAgentResult(
            chunks=all_chunks,
            strategy="recursive",
            iterations=iteration + 1,
        )


def _chunk_key(chunk: ScoredChunk) -> str:
    inner = getattr(chunk, "chunk", None)
    if inner is not None:
        cid = getattr(inner, "chunk_id", None)
        if cid:
            return str(cid)
        txt = getattr(inner, "text", "")
        return txt[:120]
    cid = getattr(chunk, "chunk_id", None) or getattr(chunk, "id", None)
    if cid:
        return str(cid)
    txt = getattr(chunk, "text", "") or getattr(chunk, "testo_chunk", "")
    return txt[:120]


def _chunk_text(chunk: ScoredChunk) -> str:
    inner = getattr(chunk, "chunk", None)
    if inner is not None:
        return getattr(inner, "text", "") or ""
    return getattr(chunk, "text", "") or getattr(chunk, "testo_chunk", "") or ""


def _extract_keywords(chunks: list[ScoredChunk], n_words: int = 5) -> str:
    text = " ".join(_chunk_text(c) for c in chunks).lower()
    words = re.findall(r"\b[a-zàèéìòù]{5,}\b", text)
    stop = {"questo", "questa", "quello", "quella", "essere", "avere", "molto",
            "anche", "ancora", "sempre", "quale", "quali", "perche", "quando"}
    freq: dict[str, int] = {}
    for w in words:
        if w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:n_words]
    return " ".join(w for w, _ in top)
