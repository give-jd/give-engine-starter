"""Tests for Embedder wrapper.

Embedder is tested with an injected fake encoder to avoid the 1 GB
sentence-transformers download during CI. The real loader path is
exercised by an integration test marked slow (skipped unless
RAG_RUN_SLOW_TESTS=1).
"""

import os

import numpy as np
import pytest

from core.shared.rag.chunking import Chunk
from core.shared.rag.embedder import Embedder, EmbedderConfig
from core.shared.rag.exceptions import EmbedderError


FAKE_DIM = 8


def _fake_encoder(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Deterministic fake encoder: char-sum seeded RNG → unit vectors."""
    out = np.zeros((len(texts), FAKE_DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        seed = sum(ord(c) for c in t) or 1
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(FAKE_DIM).astype(np.float32)
        out[i] = v / np.linalg.norm(v)
    return out


@pytest.fixture
def embedder() -> Embedder:
    cfg = EmbedderConfig(model_name="fake-model", device="cpu")
    return Embedder(cfg, encoder_fn=_fake_encoder, dimension=FAKE_DIM)


class TestEmbedderConfig:
    def test_explicit_device(self):
        cfg = EmbedderConfig(model_name="x", device="cpu")
        assert cfg.device == "cpu"

    def test_resolve_device_auto(self):
        cfg = EmbedderConfig(model_name="x", device=None)
        assert cfg.resolve_device() in {"cpu", "cuda", "mps"}


class TestEmbedder:
    def test_embed_query_returns_vector_of_correct_dimension(self, embedder: Embedder):
        v = embedder.embed_query("ciao mondo")
        assert isinstance(v, np.ndarray)
        assert v.shape == (FAKE_DIM,)
        assert v.dtype == np.float32

    def test_embed_query_returns_unit_vector(self, embedder: Embedder):
        v = embedder.embed_query("test")
        assert abs(np.linalg.norm(v) - 1.0) < 1e-5

    def test_embed_query_is_deterministic(self, embedder: Embedder):
        v1 = embedder.embed_query("query stabile")
        v2 = embedder.embed_query("query stabile")
        assert np.allclose(v1, v2)

    def test_embed_chunks_returns_list_of_vectors(self, embedder: Embedder):
        chunks = [
            Chunk.create(text=f"chunk {i}", metadata={}, sequence=i)
            for i in range(5)
        ]
        vectors = embedder.embed_chunks(chunks)
        assert len(vectors) == 5
        assert all(v.shape == (FAKE_DIM,) for v in vectors)

    def test_embed_chunks_respects_batch_size(self, embedder: Embedder):
        chunks = [
            Chunk.create(text=f"t{i}", metadata={}, sequence=i)
            for i in range(50)
        ]
        vectors = embedder.embed_chunks(chunks, batch_size=7)
        assert len(vectors) == 50

    def test_embed_empty_chunks_returns_empty_list(self, embedder: Embedder):
        assert embedder.embed_chunks([]) == []

    def test_dimension_property(self, embedder: Embedder):
        assert embedder.dimension == FAKE_DIM

    def test_batch_size_zero_raises(self, embedder: Embedder):
        chunks = [Chunk.create(text="x", metadata={}, sequence=0)]
        with pytest.raises(EmbedderError):
            embedder.embed_chunks(chunks, batch_size=0)

    def test_progress_callback_invoked(self, embedder: Embedder):
        chunks = [
            Chunk.create(text=f"t{i}", metadata={}, sequence=i)
            for i in range(10)
        ]
        seen: list[tuple[int, int]] = []

        def cb(done: int, total: int) -> None:
            seen.append((done, total))

        embedder.embed_chunks(chunks, batch_size=3, progress_callback=cb)
        assert seen, "progress callback was never called"
        assert seen[-1] == (10, 10)


class TestKnownDimensions:
    def test_e5_base_known_dim(self):
        cfg = EmbedderConfig(model_name="multilingual-e5-base", device="cpu")
        emb = Embedder(cfg, encoder_fn=_fake_encoder)  # dim auto from known table
        assert emb.dimension == 768

    def test_bge_m3_known_dim(self):
        cfg = EmbedderConfig(model_name="bge-m3", device="cpu")
        emb = Embedder(cfg, encoder_fn=_fake_encoder)
        assert emb.dimension == 1024


class TestEncoderError:
    def test_encoder_raising_is_wrapped(self):
        def boom(texts: list[str], batch_size: int = 32) -> np.ndarray:
            raise RuntimeError("model crash")

        cfg = EmbedderConfig(model_name="x", device="cpu")
        emb = Embedder(cfg, encoder_fn=boom, dimension=FAKE_DIM)
        with pytest.raises(EmbedderError):
            emb.embed_query("x")


@pytest.mark.skipif(
    os.environ.get("RAG_RUN_SLOW_TESTS") != "1",
    reason="slow integration test — set RAG_RUN_SLOW_TESTS=1 to enable",
)
class TestRealModelIntegration:
    def test_real_e5_base_loads_and_embeds(self):
        cfg = EmbedderConfig(model_name="intfloat/multilingual-e5-base", device="cpu")
        emb = Embedder(cfg)
        v = emb.embed_query("ciao mondo")
        assert v.shape == (768,)
