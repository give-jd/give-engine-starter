"""Chunking strategies for RAG indexing.

Three strategies:
- SEMANTIC_AWARE (default): recursive splitter that respects italian
  paragraph and section markers.
- FIXED_SIZE: deterministic fixed-width chunks with overlap.
- STRUCTURAL: pattern-matched sections for known document types
  (sentenze, bandi, ...).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.shared.rag.exceptions import ChunkingError


# Separators tuned for italian legal/administrative text. The splitter walks
# the list in order, falling back to finer-grained separators if a chunk is
# still too large.
_IT_SEPARATORS: list[str] = [
    "\n\n\n",
    "\n\n",
    "\nArticolo ",
    "\nArt. ",
    "\nCAPO ",
    "\nTITOLO ",
    "\nSezione ",
    "\n",
    ". ",
    "; ",
    ", ",
    " ",
    "",
]


_SENTENZA_SECTIONS: tuple[str, ...] = (
    "Svolgimento del processo",
    "Fatto",
    "In fatto",
    "Motivi della decisione",
    "Diritto",
    "In diritto",
    "Dispositivo",
    "P.Q.M.",
    "Per questi motivi",
)


class ChunkStrategy(Enum):
    SEMANTIC_AWARE = "semantic_aware"
    FIXED_SIZE = "fixed_size"
    STRUCTURAL = "structural"


@dataclass
class Chunk:
    text: str
    metadata: dict
    chunk_id: str
    sequence: int

    @classmethod
    def create(
        cls,
        text: str,
        metadata: dict,
        sequence: int,
        chunk_id: str | None = None,
    ) -> Chunk:
        return cls(
            text=text,
            metadata=dict(metadata),
            chunk_id=chunk_id or uuid.uuid4().hex,
            sequence=sequence,
        )


@dataclass
class Chunker:
    strategy: ChunkStrategy = ChunkStrategy.SEMANTIC_AWARE
    chunk_size: int = 500
    overlap: int = 50
    _splitter: RecursiveCharacterTextSplitter | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ChunkingError(
                f"chunk_size must be > 0, got {self.chunk_size}"
            )
        if self.overlap < 0:
            raise ChunkingError(
                f"overlap must be >= 0, got {self.overlap}"
            )
        if self.overlap >= self.chunk_size:
            raise ChunkingError(
                f"overlap ({self.overlap}) must be < chunk_size "
                f"({self.chunk_size})"
            )

    def chunk_document(self, text: str, metadata: dict) -> list[Chunk]:
        if not text or not text.strip():
            return []

        if self.strategy == ChunkStrategy.SEMANTIC_AWARE:
            return self._chunk_semantic(text, metadata)
        if self.strategy == ChunkStrategy.FIXED_SIZE:
            return self._chunk_fixed(text, metadata)
        if self.strategy == ChunkStrategy.STRUCTURAL:
            return self._chunk_structural(text, metadata)
        raise ChunkingError(f"unknown strategy: {self.strategy}")

    def _chunk_semantic(self, text: str, metadata: dict) -> list[Chunk]:
        if self._splitter is None:
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.overlap,
                separators=_IT_SEPARATORS,
                keep_separator=True,
            )
        pieces = self._splitter.split_text(text)
        return [
            Chunk.create(text=p, metadata=metadata, sequence=i)
            for i, p in enumerate(pieces)
            if p.strip()
        ]

    def _chunk_fixed(self, text: str, metadata: dict) -> list[Chunk]:
        step = self.chunk_size - self.overlap
        chunks: list[Chunk] = []
        for i, start in enumerate(range(0, len(text), step)):
            piece = text[start : start + self.chunk_size]
            if not piece.strip():
                continue
            chunks.append(Chunk.create(text=piece, metadata=metadata, sequence=i))
            if start + self.chunk_size >= len(text):
                break
        return chunks

    def _chunk_structural(self, text: str, metadata: dict) -> list[Chunk]:
        pattern = re.compile(
            r"^\s*(" + "|".join(re.escape(s) for s in _SENTENZA_SECTIONS) + r")\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            return self._chunk_semantic(text, metadata)

        chunks: list[Chunk] = []
        for i, match in enumerate(matches):
            section_name = match.group(1)
            section_start = match.end()
            section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_body = text[section_start:section_end].strip()
            if not section_body:
                continue
            section_meta = {**metadata, "section": _canonical_section(section_name)}
            chunks.append(
                Chunk.create(text=section_body, metadata=section_meta, sequence=i)
            )
        return chunks


def _canonical_section(raw: str) -> str:
    raw_norm = raw.strip().lower()
    for canonical in _SENTENZA_SECTIONS:
        if canonical.lower() == raw_norm:
            return canonical
    return raw.strip()
