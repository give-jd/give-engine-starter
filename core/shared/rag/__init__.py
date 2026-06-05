"""Gi.Ve shared RAG module.

Master implementation lives in `give-engine/core/shared/rag/`.
Vendored copy in `atheneo-pro/server/core/shared/rag/` (sync via
`scripts/sync-rag-from-give-engine.sh`).

Spec autoritativa: `givegroup-knowledge/shared/MODULO-CORE-SHARED-RAG.md`.
"""

from pathlib import Path

__all__ = ["RAG_VERSION"]


def _read_version() -> str:
    version_file = Path(__file__).parent / "RAG_VERSION"
    return version_file.read_text(encoding="utf-8").strip()


RAG_VERSION: str = _read_version()
