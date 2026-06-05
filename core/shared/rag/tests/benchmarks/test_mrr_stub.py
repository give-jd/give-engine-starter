"""MRR@10 benchmark stub.

v0.1 ships a stub that runs against a synthetic micro-dataset to sanity
check the wiring chain (chunker → embedder → vector_store → retriever)
without requiring the real italian bandi PNRR dataset.

Spec target (MODULO-CORE-SHARED-RAG.md):
- MRR@10 >= 0.65 with multilingual-e5-base on real bandi-PNRR test set
- MRR@10 >= 0.78 with bge-m3 on the same set

The real dataset + thresholds land in v0.2. Until then this stub just
verifies the retrieval pipeline returns the gold chunk in top-K.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.shared.rag.chunking import Chunk
from core.shared.rag.embedder import Embedder, EmbedderConfig
from core.shared.rag.retriever import Retriever
from core.shared.rag.vector_store import VectorStore


DIM = 8


def _topic_encoder(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Encoder that maps text to a topic basis vector (+ small noise)."""
    topics = {
        "fattura": 0, "iva": 0, "fiscale": 0,
        "ordine": 1, "magazzino": 1, "spedizione": 1,
        "ricetta": 2, "paziente": 2, "diagnosi": 2,
        "bando": 3, "pnrr": 3, "finanziamento": 3,
    }
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        tlow = t.lower()
        topic_id = 4
        for kw, tid in topics.items():
            if kw in tlow:
                topic_id = tid
                break
        v = np.zeros(DIM, dtype=np.float32)
        v[topic_id] = 1.0
        rng = np.random.default_rng(sum(ord(c) for c in t) or 1)
        v += rng.standard_normal(DIM).astype(np.float32) * 0.01
        out[i] = v / np.linalg.norm(v)
    return out


GOLD_DATASET: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "Come gestisco l'IVA in una fattura?",
        "gold-fiscale",
        [
            ("gold-fiscale", "L'IVA si applica alla fattura secondo aliquote."),
            ("d-ordine", "L'ordine arriva al magazzino per spedizione."),
            ("d-ricetta", "La ricetta del paziente contiene la diagnosi."),
            ("d-bando", "Il bando PNRR offre finanziamento per imprese."),
        ],
    ),
    (
        "Quale finanziamento c'è nel bando PNRR?",
        "gold-bando",
        [
            ("d-fiscale", "L'IVA si applica alla fattura secondo aliquote."),
            ("d-ordine", "L'ordine arriva al magazzino per spedizione."),
            ("d-ricetta", "La ricetta del paziente contiene la diagnosi."),
            ("gold-bando", "Il bando PNRR offre finanziamento per imprese."),
        ],
    ),
    (
        "Dove si trova l'ordine in magazzino?",
        "gold-ordine",
        [
            ("d-fiscale", "L'IVA si applica alla fattura secondo aliquote."),
            ("gold-ordine", "L'ordine arriva al magazzino per spedizione."),
            ("d-ricetta", "La ricetta del paziente contiene la diagnosi."),
            ("d-bando", "Il bando PNRR offre finanziamento per imprese."),
        ],
    ),
]


def _compute_mrr_at_k(retriever: Retriever, k: int = 10) -> float:
    reciprocal_ranks: list[float] = []
    for query, gold_id, _docs in GOLD_DATASET:
        results = retriever.retrieve(query, top_k=k, min_score=0.0)
        rank = next(
            (i + 1 for i, sc in enumerate(results) if sc.chunk.chunk_id == gold_id),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


@pytest.mark.benchmark
class TestMRRStub:
    def test_synthetic_pipeline_finds_gold_in_top_k(self, tmp_path: Path):
        store = VectorStore(db_path=tmp_path / "bench.db", dimension=DIM)
        cfg = EmbedderConfig(model_name="fake", device="cpu")
        embedder = Embedder(cfg, encoder_fn=_topic_encoder, dimension=DIM)

        seen_ids: set[str] = set()
        chunks_to_index: list[Chunk] = []
        vectors_to_index: list[np.ndarray] = []
        for _q, _gold, docs in GOLD_DATASET:
            for cid, text in docs:
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                chunks_to_index.append(
                    Chunk(text=text, metadata={}, chunk_id=cid, sequence=len(chunks_to_index))
                )
                vectors_to_index.append(_topic_encoder([text])[0])
        store.add_chunks(
            chunks=chunks_to_index,
            vectors=vectors_to_index,
            document_id="bench-doc",
            filename="bench.txt",
            sha256="b" * 64,
        )

        retriever = Retriever(vector_store=store, embedder=embedder)
        mrr = _compute_mrr_at_k(retriever, k=10)
        # Stub purpose: verify chunker→embedder→store→retriever pipeline
        # actually returns the gold chunk in top-K. Real MRR thresholds
        # (0.65 e5-base / 0.78 bge-m3) require the bandi-PNRR dataset
        # which lands in v0.2.
        assert mrr > 0.0, (
            f"pipeline did not return any gold chunk in top-K: mrr={mrr}"
        )

        # Also verify each query's gold chunk appears in top-K.
        for query, gold_id, _docs in GOLD_DATASET:
            results = retriever.retrieve(query, top_k=10, min_score=0.0)
            returned_ids = {sc.chunk.chunk_id for sc in results}
            assert gold_id in returned_ids, (
                f"gold chunk {gold_id} missing from top-10 for query: {query!r}"
            )

    @pytest.mark.skip(
        reason="real bandi-PNRR dataset lands in v0.2 — see MODULO-CORE-SHARED-RAG.md"
    )
    def test_mrr_at_10_meets_threshold_e5_base(self):
        """v0.2: MRR@10 >= 0.65 with multilingual-e5-base on bandi-PNRR."""

    @pytest.mark.skip(
        reason="real bandi-PNRR dataset lands in v0.2 — see MODULO-CORE-SHARED-RAG.md"
    )
    def test_mrr_at_10_meets_threshold_bge_m3(self):
        """v0.2: MRR@10 >= 0.78 with bge-m3 on bandi-PNRR."""
