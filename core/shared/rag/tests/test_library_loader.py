"""Tests for LibraryLoader.

The loader fetches a manifest of pre-indexed skills, downloads archives,
verifies signatures, and installs chunks+vectors into a VectorStore. v0.1
uses a stub manifest fixture and a stub signature verifier.
"""

import gzip
import json
import tarfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from core.shared.rag.exceptions import LibraryError
from core.shared.rag.library_loader import LibraryLoader, LibrarySkill
from core.shared.rag.vector_store import VectorStore


FIXTURE_MANIFEST = (
    Path(__file__).resolve().parent.parent / "fixtures" / "library_manifest.json"
)


def _build_fake_skill_archive(
    out_path: Path,
    *,
    slug: str,
    embedder_model: str,
    dimension: int,
    chunks_count: int = 3,
) -> None:
    chunks_jsonl = "\n".join(
        json.dumps(
            {
                "chunk_id": f"{slug}-{i}",
                "text": f"chunk {i} for {slug}",
                "metadata": {"skill": slug, "page": i + 1},
                "sequence": i,
            }
        )
        for i in range(chunks_count)
    )
    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((chunks_count, dimension)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

    manifest = {
        "slug": slug,
        "embedder_model": embedder_model,
        "dimension": dimension,
        "chunks_count": chunks_count,
        "version": "2026-W22",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in [
            ("manifest.json", json.dumps(manifest).encode("utf-8")),
            ("chunks.jsonl", chunks_jsonl.encode("utf-8")),
        ]:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, BytesIO(content))
        npy_buf = BytesIO()
        np.save(npy_buf, vectors)
        npy_buf.seek(0)
        data = npy_buf.read()
        info = tarfile.TarInfo(name="vectors.npy")
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    out_path.write_bytes(gzip.compress(buf.getvalue()))


@pytest.fixture
def loader(tmp_path: Path) -> LibraryLoader:
    # Default test loader: dev_allow_stub mode per preservare backward-compat
    # con i test esistenti scritti per v0.1.
    return LibraryLoader(
        manifest_path=FIXTURE_MANIFEST,
        cache_dir=tmp_path / "cache",
        signature_mode="dev_allow_stub",
    )


class TestLibrarySkill:
    def test_skill_from_dict(self):
        skill = LibrarySkill.from_dict(
            {
                "slug": "x",
                "name": "X",
                "description": "d",
                "version": "2026-W22",
                "embedder_model": "multilingual-e5-base",
                "dimension": 768,
                "chunks_count": 10,
                "size_mb": 1.0,
                "signature": "STUB",
                "download_url": "https://example.com/x.atheneo-light",
            }
        )
        assert skill.slug == "x"
        assert skill.dimension == 768


class TestListAvailable:
    def test_list_returns_all_skills_from_manifest(self, loader: LibraryLoader):
        skills = loader.list_available_skills()
        assert len(skills) >= 3
        slugs = {s.slug for s in skills}
        assert "manuali-anthropic" in slugs
        assert "bandi-pnrr" in slugs

    def test_filter_by_embedder_model(self, loader: LibraryLoader):
        light_only = loader.list_available_skills(
            embedder_model="multilingual-e5-base"
        )
        for s in light_only:
            assert s.embedder_model == "multilingual-e5-base"


class TestInstallSkill:
    def test_install_loads_chunks_into_store(self, tmp_path: Path, loader: LibraryLoader):
        archive = tmp_path / "test-skill.atheneo-light"
        _build_fake_skill_archive(
            archive, slug="test-skill", embedder_model="multilingual-e5-base",
            dimension=768, chunks_count=5,
        )
        store = VectorStore(db_path=tmp_path / "test.db", dimension=768)
        loader.install_skill(archive, vector_store=store)
        stats = store.stats()
        assert stats["total_chunks"] == 5
        assert stats["total_documents"] == 1

    def test_install_rejects_dimension_mismatch(self, tmp_path: Path, loader: LibraryLoader):
        archive = tmp_path / "wrong-dim.atheneo-light"
        _build_fake_skill_archive(
            archive, slug="wrong", embedder_model="multilingual-e5-base",
            dimension=768, chunks_count=2,
        )
        store = VectorStore(db_path=tmp_path / "store-1024.db", dimension=1024)
        with pytest.raises(LibraryError) as excinfo:
            loader.install_skill(archive, vector_store=store)
        assert "dimension" in str(excinfo.value).lower()


class TestDownloadStub:
    def test_download_skill_uses_fetcher_injection(self, tmp_path: Path):
        archive_target = tmp_path / "downloaded.atheneo-light"
        _build_fake_skill_archive(
            archive_target, slug="x", embedder_model="multilingual-e5-base",
            dimension=768, chunks_count=2,
        )

        def fake_fetcher(url: str, dest: Path) -> Path:
            dest.write_bytes(archive_target.read_bytes())
            return dest

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            fetcher=fake_fetcher,
        )
        path = loader.download_skill("manuali-anthropic", verify_signature=False)
        assert path.exists()
        assert path.read_bytes() == archive_target.read_bytes()

    def test_download_unknown_slug_raises(self, tmp_path: Path, loader: LibraryLoader):
        with pytest.raises(LibraryError) as excinfo:
            loader.download_skill("nonexistent-skill")
        assert excinfo.value.slug == "nonexistent-skill"

    def test_signature_verification_dev_allow_stub_accepts_stub(
        self, tmp_path: Path, loader: LibraryLoader
    ):
        # `loader` fixture è in dev_allow_stub mode
        archive = tmp_path / "ok.atheneo-light"
        _build_fake_skill_archive(
            archive, slug="manuali-anthropic", embedder_model="multilingual-e5-base",
            dimension=768, chunks_count=2,
        )
        assert loader.verify_signature(archive, signature="STUB-NOT-VERIFIED-V0.1") is True
        assert loader.verify_signature(archive, signature="") is False


class TestSignatureModes:
    def _archive(self, tmp_path: Path) -> Path:
        p = tmp_path / "x.atheneo-light"
        _build_fake_skill_archive(
            p, slug="x", embedder_model="multilingual-e5-base",
            dimension=768, chunks_count=1,
        )
        return p

    def test_strict_mode_rejects_stub_signature(self, tmp_path: Path):
        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode="strict",
        )
        archive = self._archive(tmp_path)
        assert loader.verify_signature(archive, "STUB-NOT-VERIFIED-V0.1") is False

    def test_strict_mode_with_fake_verifier_accepts_valid_gpg(
        self, tmp_path: Path
    ):
        def accept_all(path, sig):
            return True

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode="strict",
            verifier=accept_all,
        )
        archive = self._archive(tmp_path)
        assert loader.verify_signature(
            archive, "-----BEGIN PGP SIGNATURE-----\nabc\n-----END PGP SIGNATURE-----"
        ) is True

    def test_strict_mode_with_fake_verifier_rejects_invalid_gpg(
        self, tmp_path: Path
    ):
        def reject_all(path, sig):
            return False

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode="strict",
            verifier=reject_all,
        )
        archive = self._archive(tmp_path)
        assert loader.verify_signature(
            archive, "-----BEGIN PGP SIGNATURE-----\nbad\n-----END PGP SIGNATURE-----"
        ) is False

    def test_unknown_signature_mode_raises(self, tmp_path: Path):
        from core.shared.rag.exceptions import LibraryError

        with pytest.raises(LibraryError):
            LibraryLoader(
                manifest_path=FIXTURE_MANIFEST,
                cache_dir=tmp_path / "cache",
                signature_mode="invalid_mode_x",
            )

    def test_default_mode_is_strict(self, tmp_path: Path):
        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
        )
        assert loader.signature_mode == "strict"

    def test_verifier_exception_treated_as_invalid(self, tmp_path: Path):
        def boom(path, sig):
            raise RuntimeError("gpg crashed")

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode="strict",
            verifier=boom,
        )
        archive = self._archive(tmp_path)
        assert loader.verify_signature(archive, "-----BEGIN PGP SIGNATURE-----\nx\n-----END PGP SIGNATURE-----") is False
