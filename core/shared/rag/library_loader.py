"""Library loader for pre-indexed Atheneo skills.

Skills are tar.gz archives (`.atheneo-light` / `.atheneo-pro`) distributed
via the Gi.Ve CDN. Each archive contains:

- `manifest.json` — slug, embedder_model, dimension, chunks_count, version
- `chunks.jsonl` — one Chunk per line (chunk_id, text, metadata, sequence)
- `vectors.npy` — float32 array shape (chunks_count, dimension)

v0.1: manifest read from a local file or remote URL. GPG signature
verification is a stub — real implementation lands in v0.2.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np

from core.shared.rag.chunking import Chunk
from core.shared.rag.exceptions import LibraryError
from core.shared.rag.vector_store import VectorStore


Fetcher = Callable[[str, Path], Path]
SignatureVerifier = Callable[[Path, str], bool]


# Modalità verifica firma:
# - "strict" (default produzione): solo firme GPG valide accettate.
#   Firme STUB-* sono rifiutate.
# - "dev_allow_stub": firme STUB-* accettate (dev/test) oltre alle GPG valide.
SIGNATURE_MODE_STRICT = "strict"
SIGNATURE_MODE_DEV_ALLOW_STUB = "dev_allow_stub"
_KNOWN_SIGNATURE_MODES = (SIGNATURE_MODE_STRICT, SIGNATURE_MODE_DEV_ALLOW_STUB)


def _gpg_verify_subprocess(archive_path: Path, signature: str) -> bool:
    """Default GPG verifier via subprocess `gpg --verify`.

    Accetta `signature` come stringa ASCII-armored della firma detached.
    Salva la firma in tmp file e chiama gpg per verificarla contro archive.
    Ritorna True solo se gpg ritorna exit code 0.

    Requisito: keyring del firmatario Gi.Ve già importato nel sistema
    (gpg --import key.asc al setup ricetta).
    """
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sig", delete=False
        ) as sig_file:
            sig_file.write(signature)
            sig_path = sig_file.name
    except OSError:
        return False

    try:
        result = subprocess.run(
            ["gpg", "--verify", sig_path, str(archive_path)],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # FileNotFoundError = gpg binary mancante
        return False
    finally:
        try:
            Path(sig_path).unlink(missing_ok=True)
        except OSError:
            pass


@dataclass
class LibrarySkill:
    slug: str
    name: str
    description: str
    version: str  # e.g. "2026-W22"
    embedder_model: str
    dimension: int
    chunks_count: int
    size_mb: float
    signature: str
    download_url: str

    @classmethod
    def from_dict(cls, data: dict) -> LibrarySkill:
        return cls(
            slug=data["slug"],
            name=data["name"],
            description=data["description"],
            version=data["version"],
            embedder_model=data["embedder_model"],
            dimension=int(data["dimension"]),
            chunks_count=int(data["chunks_count"]),
            size_mb=float(data["size_mb"]),
            signature=data.get("signature", ""),
            download_url=data["download_url"],
        )


def _default_http_fetcher(url: str, dest: Path) -> Path:
    """Default HTTP fetcher. httpx imported lazily."""
    import httpx  # type: ignore

    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                f.write(chunk)
    return dest


class LibraryLoader:
    def __init__(
        self,
        manifest_path: Path | None = None,
        manifest_url: str | None = None,
        cache_dir: Path | None = None,
        fetcher: Fetcher | None = None,
        signature_mode: str = SIGNATURE_MODE_STRICT,
        verifier: SignatureVerifier | None = None,
    ) -> None:
        if manifest_path is None and manifest_url is None:
            raise LibraryError("either manifest_path or manifest_url is required")
        if signature_mode not in _KNOWN_SIGNATURE_MODES:
            raise LibraryError(
                f"unknown signature_mode: {signature_mode}. "
                f"Supported: {', '.join(_KNOWN_SIGNATURE_MODES)}"
            )
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.manifest_url = manifest_url
        self.cache_dir = (
            Path(cache_dir) if cache_dir else Path.home() / ".givengine" / "library"
        )
        self.fetcher: Fetcher = fetcher or _default_http_fetcher
        self.signature_mode = signature_mode
        self._verifier: SignatureVerifier = verifier or _gpg_verify_subprocess

    def list_available_skills(
        self, embedder_model: str | None = None
    ) -> list[LibrarySkill]:
        manifest = self._read_manifest()
        skills = [LibrarySkill.from_dict(d) for d in manifest.get("skills", [])]
        if embedder_model is not None:
            skills = [s for s in skills if s.embedder_model == embedder_model]
        return skills

    def download_skill(self, slug: str, verify_signature: bool = True) -> Path:
        skill = self._find_skill(slug)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / f"{skill.slug}-{skill.version}.atheneo-light"
        if not target.exists():
            self.fetcher(skill.download_url, target)
        if verify_signature and not self.verify_signature(target, skill.signature):
            raise LibraryError(
                f"signature verification failed for {slug}", slug=slug
            )
        return target

    def install_skill(self, skill_path: Path, vector_store: VectorStore) -> None:
        if not skill_path.exists():
            raise LibraryError(f"skill archive not found: {skill_path}")
        manifest, chunks, vectors = self._unpack_archive(skill_path)

        if int(manifest.get("dimension", -1)) != vector_store.dimension:
            raise LibraryError(
                f"dimension mismatch: skill={manifest.get('dimension')} "
                f"store={vector_store.dimension}",
                slug=manifest.get("slug"),
            )
        if vectors.shape[0] != len(chunks):
            raise LibraryError(
                f"vector count {vectors.shape[0]} != chunks count {len(chunks)}",
                slug=manifest.get("slug"),
            )

        sha = hashlib.sha256(skill_path.read_bytes()).hexdigest()
        vector_store.add_chunks(
            chunks=chunks,
            vectors=[vectors[i] for i in range(vectors.shape[0])],
            document_id=f"skill:{manifest['slug']}:{manifest.get('version', '')}",
            filename=skill_path.name,
            sha256=sha,
        )

    def verify_signature(self, archive_path: Path, signature: str) -> bool:
        """Verifica firma archive secondo signature_mode configurato.

        - In modalità "dev_allow_stub": accetta `STUB-*` come firma valida.
        - In modalità "strict" (default): rifiuta `STUB-*`, delega a verifier
          GPG (subprocess gpg --verify di default).

        Sempre False se signature vuota.
        """
        if not signature:
            return False
        if signature.startswith("STUB-"):
            return self.signature_mode == SIGNATURE_MODE_DEV_ALLOW_STUB
        # Firma non-stub → delega al verifier (GPG vero o iniettato)
        try:
            return bool(self._verifier(archive_path, signature))
        except Exception:
            return False

    def _read_manifest(self) -> dict:
        if self.manifest_path is not None:
            if not self.manifest_path.exists():
                raise LibraryError(f"manifest file not found: {self.manifest_path}")
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        local = self.cache_dir / "library_manifest.json"
        self.fetcher(self.manifest_url or "", local)
        return json.loads(local.read_text(encoding="utf-8"))

    def _find_skill(self, slug: str) -> LibrarySkill:
        for s in self.list_available_skills():
            if s.slug == slug:
                return s
        raise LibraryError(f"unknown skill slug: {slug}", slug=slug)

    def _unpack_archive(
        self, archive_path: Path
    ) -> tuple[dict, list[Chunk], np.ndarray]:
        try:
            raw = gzip.decompress(archive_path.read_bytes())
            buf = BytesIO(raw)
            with tarfile.open(fileobj=buf, mode="r") as tar:
                manifest_data = _read_tar_member(tar, "manifest.json")
                chunks_data = _read_tar_member(tar, "chunks.jsonl")
                vectors_data = _read_tar_member(tar, "vectors.npy")
        except (gzip.BadGzipFile, tarfile.TarError, KeyError) as exc:
            raise LibraryError(f"corrupt skill archive: {exc}") from exc

        manifest = json.loads(manifest_data.decode("utf-8"))
        chunks: list[Chunk] = []
        for line in chunks_data.decode("utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            chunks.append(
                Chunk(
                    text=data["text"],
                    metadata=data.get("metadata", {}),
                    chunk_id=data["chunk_id"],
                    sequence=int(data["sequence"]),
                )
            )
        vectors = np.load(BytesIO(vectors_data))
        return manifest, chunks, vectors


def _read_tar_member(tar: tarfile.TarFile, name: str) -> bytes:
    member = tar.getmember(name)
    f = tar.extractfile(member)
    if f is None:
        raise LibraryError(f"missing archive member: {name}")
    return f.read()
