"""Coordinator di sync: orchestra manifest + diff + envelope su una sorgente.

`SyncCoordinator` è il glue riusabile fra il modulo sync e una ricetta. La
ricetta implementa `SyncSource` (come legge/scrive i propri record cifrati); il
coordinator costruisce il manifest, calcola il piano contro un peer, sigilla gli
envelope da inviare e applica quelli ricevuti con politica Last-Write-Wins.

Sicurezza dati: `import_envelopes` ricontrolla `updated_at` locale prima di
applicare. Non sovrascrive mai un record locale più recente; un record con pari
timestamp ma contenuto diverso è segnalato come conflitto, non sovrascritto.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from core.shared.sync.envelope import open_record, seal_record
from core.shared.sync.exceptions import SyncError
from core.shared.sync.manifest import (
    RecordMeta,
    SyncPlan,
    build_manifest,
    diff_manifests,
)


class SyncSource(Protocol):
    """Sorgente record di una ricetta, disaccoppiata dal coordinator.

    Il payload restituito è il contenuto da cifrare nell'envelope (la ricetta
    decide se è già cifrato at-rest o plaintext da proteggere solo in transito).
    """

    def manifest_records(self) -> Iterable[tuple[str, bytes, int]]:
        """Tutti i record come (record_id, payload, updated_at epoch)."""
        ...

    def get_payload(self, record_id: str) -> tuple[bytes, int]:
        """Payload + updated_at di un singolo record."""
        ...

    def apply_record(self, record_id: str, payload: bytes, updated_at: int) -> None:
        """Applica un record ricevuto (insert o update)."""
        ...


@dataclass(frozen=True)
class ImportResult:
    """Esito di `import_envelopes`.

    Attributes:
        applied: record_id scritti (nuovi o più recenti del locale).
        skipped_older: record_id ignorati perché non più recenti / identici.
        conflicts: record_id con pari timestamp ma contenuto diverso (NON scritti).
        failed_indices: indici degli envelope non apribili (tamper/chiave errata).
    """

    applied: tuple[str, ...]
    skipped_older: tuple[str, ...]
    conflicts: tuple[str, ...]
    failed_indices: tuple[int, ...]


class SyncCoordinator:
    """Orchestratore di sync per una `SyncSource` e una master key condivisa."""

    def __init__(self, source: SyncSource, key: bytes) -> None:
        self._source = source
        self._key = key

    def local_manifest(self) -> dict[str, RecordMeta]:
        """Costruisce il manifest dei record locali."""
        return build_manifest(self._source.manifest_records())

    def plan_against(self, remote_manifest: dict[str, RecordMeta]) -> SyncPlan:
        """Calcola il piano sync confrontando il locale col manifest remoto."""
        return diff_manifests(self.local_manifest(), remote_manifest)

    def export_envelopes(self, record_ids: Sequence[str]) -> list[bytes]:
        """Sigilla in envelope i record richiesti (es. SyncPlan.to_send)."""
        envelopes: list[bytes] = []
        for record_id in record_ids:
            payload, updated_at = self._source.get_payload(record_id)
            envelopes.append(seal_record(record_id, payload, updated_at, self._key))
        return envelopes

    def import_envelopes(self, envelopes: Iterable[bytes]) -> ImportResult:
        """Apre e applica envelope ricevuti con politica Last-Write-Wins.

        Non sovrascrive record locali più recenti; pari timestamp + contenuto
        diverso → conflitto segnalato, non scritto. Envelope non autentici sono
        contati (per indice) e non applicati.
        """
        local = self.local_manifest()
        applied: list[str] = []
        skipped: list[str] = []
        conflicts: list[str] = []
        failed: list[int] = []

        for index, envelope in enumerate(envelopes):
            try:
                record_id, payload, updated_at = open_record(envelope, self._key)
            except SyncError:
                failed.append(index)
                continue

            current = local.get(record_id)
            if current is None or updated_at > current.updated_at:
                try:
                    self._source.apply_record(record_id, payload, updated_at)
                except SyncError:
                    # Payload incompatibile col source (es. record_id malformato,
                    # campi NOT NULL mancanti): il record fallisce da solo, il
                    # batch prosegue. No DoS da singolo envelope malevolo.
                    failed.append(index)
                    continue
                applied.append(record_id)
                # Aggiorna lo stato in-memory: iterazioni successive sullo stesso
                # record_id nello stesso batch devono vedere ciò che è appena
                # stato scritto, altrimenti un envelope più vecchio/conflittuale
                # nello stesso batch potrebbe sovrascrivere silenziosamente (LWW
                # drift intra-batch).
                local[record_id] = RecordMeta(
                    record_id=record_id,
                    content_hash=hashlib.sha256(payload).hexdigest(),
                    updated_at=updated_at,
                )
            elif updated_at == current.updated_at:
                incoming_hash = hashlib.sha256(payload).hexdigest()
                if incoming_hash != current.content_hash:
                    conflicts.append(record_id)  # mai sovrascritto
                else:
                    skipped.append(record_id)  # identico
            else:
                skipped.append(record_id)  # locale più recente

        return ImportResult(
            applied=tuple(applied),
            skipped_older=tuple(skipped),
            conflicts=tuple(conflicts),
            failed_indices=tuple(failed),
        )
