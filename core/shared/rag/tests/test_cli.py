"""Tests for CLI entry points."""

import gzip
import json
import tarfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from core.shared.rag import cli


def _build_fake_skill_archive(out_path: Path, *, slug: str, dim: int, n: int = 3) -> None:
    chunks_jsonl = "\n".join(
        json.dumps(
            {
                "chunk_id": f"{slug}-{i}",
                "text": f"chunk {i}",
                "metadata": {"page": i + 1},
                "sequence": i,
            }
        )
        for i in range(n)
    )
    rng = np.random.default_rng(0)
    vectors = rng.standard_normal((n, dim)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    manifest = {
        "slug": slug, "embedder_model": "multilingual-e5-base",
        "dimension": dim, "chunks_count": n, "version": "2026-W22",
    }
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in [
            ("manifest.json", json.dumps(manifest).encode()),
            ("chunks.jsonl", chunks_jsonl.encode()),
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
def fixture_manifest() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "library_manifest.json"
    )


class TestLibraryList:
    def test_library_list_prints_skills(self, capsys, fixture_manifest: Path):
        rc = cli.main(
            ["library-list", "--manifest", str(fixture_manifest)]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "manuali-anthropic" in out
        assert "bandi-pnrr" in out

    def test_library_list_filter_by_embedder(self, capsys, fixture_manifest: Path):
        rc = cli.main(
            [
                "library-list",
                "--manifest", str(fixture_manifest),
                "--embedder", "bge-m3",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "manuali-anthropic-pro" in out
        assert "bandi-pnrr" not in out


class TestLibraryFetch:
    def test_fetch_existing_skill_runs(
        self, capsys, tmp_path: Path, fixture_manifest: Path
    ):
        archive = tmp_path / "downloaded.atheneo-light"
        _build_fake_skill_archive(archive, slug="manuali-anthropic", dim=768, n=2)

        def fake_fetcher(url: str, dest: Path) -> Path:
            dest.write_bytes(archive.read_bytes())
            return dest

        rc = cli.main(
            [
                "library-fetch",
                "--slug", "manuali-anthropic",
                "--manifest", str(fixture_manifest),
                "--cache-dir", str(tmp_path / "cache"),
                "--no-verify-signature",
            ],
            fetcher=fake_fetcher,
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "manuali-anthropic" in out
        cache_files = list((tmp_path / "cache").glob("manuali-anthropic-*.atheneo-light"))
        assert len(cache_files) == 1

    def test_fetch_unknown_slug_returns_error_code(
        self, capsys, tmp_path: Path, fixture_manifest: Path
    ):
        rc = cli.main(
            [
                "library-fetch",
                "--slug", "nonexistent",
                "--manifest", str(fixture_manifest),
                "--cache-dir", str(tmp_path / "cache"),
            ]
        )
        err = capsys.readouterr().err
        assert rc != 0
        assert "nonexistent" in err


class TestVerifyLibrary:
    def test_verify_library_reports_status(
        self, capsys, tmp_path: Path, fixture_manifest: Path
    ):
        rc = cli.main(
            [
                "verify-library",
                "--manifest", str(fixture_manifest),
                "--cache-dir", str(tmp_path / "cache"),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "0" in out or "Nessuna" in out or "non" in out.lower()


class TestRebuild:
    def test_rebuild_empty_store_runs(self, capsys, tmp_path: Path):
        rc = cli.main(
            [
                "rebuild",
                "--db", str(tmp_path / "x.db"),
                "--dimension", "768",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "768" in out

    def test_rebuild_reports_zero_chunks_initially(self, capsys, tmp_path: Path):
        db = tmp_path / "x.db"
        rc = cli.main(["rebuild", "--db", str(db), "--dimension", "8"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0" in out


class TestHelp:
    def test_no_args_shows_help_and_nonzero_exit(self, capsys):
        rc = cli.main([])
        assert rc != 0
        captured = capsys.readouterr()
        assert "library-list" in (captured.out + captured.err)
