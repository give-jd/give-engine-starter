"""Integration test della firma GPG reale.

Genera keypair GPG in GNUPGHOME temporaneo, firma archive sintetico via
`gpg --detach-sign --armor`, verifica che LibraryLoader in strict mode
accetti firma legittima e rifiuti firme tampered/sconosciute.

Eseguire con:
    RAG_RUN_SLOW_TESTS=1 pytest core/shared/rag/tests/integration/test_gpg_signature.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.shared.rag.library_loader import (
    SIGNATURE_MODE_STRICT,
    LibraryLoader,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("RAG_RUN_SLOW_TESTS") != "1"
    or shutil.which("gpg") is None,
    reason="slow integration test (richiede gpg + RAG_RUN_SLOW_TESTS=1)",
)


FIXTURE_MANIFEST = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures"
    / "library_manifest.json"
)


@pytest.fixture
def gpg_home(tmp_path: Path):
    gh = tmp_path / "gnupg"
    gh.mkdir(mode=0o700)
    env = {**os.environ, "GNUPGHOME": str(gh)}

    batch = (
        "%no-protection\n"
        "Key-Type: RSA\n"
        "Key-Length: 2048\n"
        "Name-Real: Atheneo Test Signer\n"
        "Name-Email: test@givegroup.local\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    result = subprocess.run(
        ["gpg", "--batch", "--generate-key"],
        input=batch,
        text=True,
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"gpg keygen failed: stdout={result.stdout} stderr={result.stderr}"
    )
    yield gh, env


def _sign_file(file_path: Path, env: dict) -> str:
    result = subprocess.run(
        ["gpg", "--armor", "--detach-sign", "--output", "-", str(file_path)],
        env=env,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"gpg sign failed: {result.stderr.decode(errors='replace')}"
    )
    return result.stdout.decode("utf-8")


def _gpg_verify_with_env(env: dict):
    def verify(archive_path: Path, signature: str) -> bool:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sig", delete=False
        ) as sig_file:
            sig_file.write(signature)
            sig_path = sig_file.name
        try:
            result = subprocess.run(
                ["gpg", "--verify", sig_path, str(archive_path)],
                capture_output=True,
                env=env,
                timeout=30,
            )
            return result.returncode == 0
        finally:
            Path(sig_path).unlink(missing_ok=True)

    return verify


class TestGPGSignatureReal:
    def test_valid_gpg_signature_accepted_in_strict_mode(
        self, tmp_path: Path, gpg_home
    ):
        gh, env = gpg_home
        archive = tmp_path / "skill.atheneo-light"
        archive.write_bytes(b"contenuto archivio binario sintetico")

        signature = _sign_file(archive, env)

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode=SIGNATURE_MODE_STRICT,
            verifier=_gpg_verify_with_env(env),
        )
        assert loader.verify_signature(archive, signature) is True

    def test_tampered_archive_rejected(self, tmp_path: Path, gpg_home):
        gh, env = gpg_home
        archive = tmp_path / "skill.atheneo-light"
        archive.write_bytes(b"contenuto originale")
        signature = _sign_file(archive, env)

        archive.write_bytes(b"contenuto MODIFICATO post-firma")

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode=SIGNATURE_MODE_STRICT,
            verifier=_gpg_verify_with_env(env),
        )
        assert loader.verify_signature(archive, signature) is False

    def test_tampered_signature_rejected(self, tmp_path: Path, gpg_home):
        gh, env = gpg_home
        archive = tmp_path / "skill.atheneo-light"
        archive.write_bytes(b"contenuto")
        signature = _sign_file(archive, env)

        bad_sig = signature.replace("A", "X", 5) if "A" in signature else signature + "BAD"

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode=SIGNATURE_MODE_STRICT,
            verifier=_gpg_verify_with_env(env),
        )
        assert loader.verify_signature(archive, bad_sig) is False

    def test_unknown_signer_rejected(self, tmp_path: Path, gpg_home):
        gh, env = gpg_home
        archive = tmp_path / "skill.atheneo-light"
        archive.write_bytes(b"contenuto")
        signature = _sign_file(archive, env)

        empty_gh = tmp_path / "empty_gnupg"
        empty_gh.mkdir(mode=0o700)
        empty_env = {**os.environ, "GNUPGHOME": str(empty_gh)}

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode=SIGNATURE_MODE_STRICT,
            verifier=_gpg_verify_with_env(empty_env),
        )
        assert loader.verify_signature(archive, signature) is False

    def test_stub_signature_rejected_in_strict_mode_with_real_gpg(
        self, tmp_path: Path, gpg_home
    ):
        gh, env = gpg_home
        archive = tmp_path / "skill.atheneo-light"
        archive.write_bytes(b"contenuto")

        loader = LibraryLoader(
            manifest_path=FIXTURE_MANIFEST,
            cache_dir=tmp_path / "cache",
            signature_mode=SIGNATURE_MODE_STRICT,
            verifier=_gpg_verify_with_env(env),
        )
        assert loader.verify_signature(archive, "STUB-NOT-VERIFIED-V0.1") is False
