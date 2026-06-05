"""SQLite + sqlite-vec backed vector store.

Single SQLite file per index. Schema is created on first open. Subsequent
opens validate the configured dimension against the stored dimension to
prevent silently mixing embedders (e5-base 768 vs bge-m3 1024).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sqlite_vec

from core.shared.rag.chunking import Chunk
from core.shared.rag.exceptions import VectorStoreError


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    source: str = "dense"  # "dense" | "sparse" | "hybrid"


_SCHEMA_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
)
"""

_SCHEMA_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    text TEXT NOT NULL,
    metadata JSON,
    permissions JSON,
    FOREIGN KEY (document_id) REFERENCES documents(document_id)
        ON DELETE CASCADE
)
"""

_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS store_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


class VectorStore:
    def __init__(self, db_path: Path, dimension: int) -> None:
        self.db_path = Path(db_path)
        self.dimension = int(dimension)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False: SQLite connection condivisa fra thread
        # è sicura quando combinata con WAL mode + synchronous=NORMAL
        # (richiesto da Streamlit che ricarica lo script su thread diversi
        # ad ogni rerun). Senza questo, app cross-thread crasha con
        # sqlite3.ProgrammingError.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL mode: migliora concorrenza multi-reader (es. due tab Streamlit)
        # senza compromettere durabilità. Crea file -wal e -shm accanto al .db.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

        self._ensure_schema()
        self._validate_or_record_dimension()

    def _ensure_schema(self) -> None:
        self._conn.execute(_SCHEMA_DOCUMENTS)
        self._conn.execute(_SCHEMA_CHUNKS)
        self._conn.execute(_SCHEMA_META)
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors "
            f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding FLOAT[{self.dimension}])"
        )
        self._conn.commit()

    def _validate_or_record_dimension(self) -> None:
        row = self._conn.execute(
            "SELECT value FROM store_meta WHERE key = 'dimension'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO store_meta(key, value) VALUES ('dimension', ?)",
                (str(self.dimension),),
            )
            self._conn.commit()
            return
        stored = int(row["value"])
        if stored != self.dimension:
            raise VectorStoreError(
                f"dimension mismatch on existing store {self.db_path}",
                expected=stored,
                actual=self.dimension,
            )

    def add_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[np.ndarray],
        document_id: str,
        filename: str,
        sha256: str,
        permissions: dict | None = None,
    ) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreError(
                f"chunks/vectors length mismatch: "
                f"{len(chunks)} chunks vs {len(vectors)} vectors"
            )
        for v in vectors:
            if v.shape[-1] != self.dimension:
                raise VectorStoreError(
                    "vector dimension mismatch",
                    expected=self.dimension,
                    actual=int(v.shape[-1]),
                )

        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "INSERT INTO documents(document_id, filename, sha256, metadata) "
                    "VALUES(?, ?, ?, ?)",
                    (document_id, filename, sha256, json.dumps({})),
                )
            except sqlite3.IntegrityError as exc:
                raise VectorStoreError(
                    f"document with sha256 {sha256[:12]}... already indexed"
                ) from exc

            for chunk, vector in zip(chunks, vectors):
                cur.execute(
                    "INSERT INTO chunks(chunk_id, document_id, sequence, text, "
                    "metadata, permissions) VALUES(?, ?, ?, ?, ?, ?)",
                    (
                        chunk.chunk_id,
                        document_id,
                        chunk.sequence,
                        chunk.text,
                        json.dumps(chunk.metadata),
                        json.dumps(permissions) if permissions is not None else None,
                    ),
                )
                vec_bytes = np.asarray(vector, dtype=np.float32).tobytes()
                cur.execute(
                    "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES(?, ?)",
                    (chunk.chunk_id, vec_bytes),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[ScoredChunk]:
        if query_vector.shape[-1] != self.dimension:
            raise VectorStoreError(
                "query vector dimension mismatch",
                expected=self.dimension,
                actual=int(query_vector.shape[-1]),
            )
        qbytes = np.asarray(query_vector, dtype=np.float32).tobytes()
        rows = self._conn.execute(
            """
            SELECT
                c.chunk_id, c.document_id, c.sequence, c.text, c.metadata,
                v.distance
            FROM chunk_vectors v
            JOIN chunks c ON c.chunk_id = v.chunk_id
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (qbytes, int(top_k)),
        ).fetchall()

        results: list[ScoredChunk] = []
        for row in rows:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            chunk = Chunk(
                text=row["text"],
                metadata=metadata,
                chunk_id=row["chunk_id"],
                sequence=row["sequence"],
            )
            distance = float(row["distance"])
            # sqlite-vec returns L2 distance for FLOAT[]; for unit-norm vectors
            # similarity = 1 - dist^2 / 2. Clamp to [0, 1] for sanity.
            score = max(0.0, min(1.0, 1.0 - (distance**2) / 2.0))
            results.append(ScoredChunk(chunk=chunk, score=score, source="dense"))
        return results

    def delete_document(self, document_id: str) -> None:
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            rows = cur.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchall()
            for row in rows:
                cur.execute(
                    "DELETE FROM chunk_vectors WHERE chunk_id = ?",
                    (row["chunk_id"],),
                )
            cur.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            cur.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def stats(self) -> dict:
        chunk_count = self._conn.execute(
            "SELECT COUNT(*) AS n FROM chunks"
        ).fetchone()["n"]
        doc_count = self._conn.execute(
            "SELECT COUNT(*) AS n FROM documents"
        ).fetchone()["n"]
        last_row = self._conn.execute(
            "SELECT MAX(indexed_at) AS last FROM documents"
        ).fetchone()
        return {
            "total_chunks": int(chunk_count),
            "total_documents": int(doc_count),
            "last_indexed_at": last_row["last"],
            "dimension": self.dimension,
        }

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> VectorStore:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
