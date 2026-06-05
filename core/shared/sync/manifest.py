"""Manifest e diff per sync P2P LAN-only.

Un manifest mappa `record_id -> RecordMeta` (hash + timestamp). Il diff fra
due manifest produce un `SyncPlan` con risoluzione Last-Write-Wins per
`updated_at`. Conflitto (stesso timestamp, hash diverso) è flaggato, mai
risolto silenziosamente: nessuna perdita di dati.

Nessun clock interno: il timestamp `updated_at` è fornito dal chiamante
(epoch seconds), così la logica è deterministica e testabile.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RecordMeta:
    """Metadati di un record per il confronto sync.

    Attributes:
        record_id: identificatore stabile del record.
        content_hash: sha256 esadecimale del payload.
        updated_at: epoch seconds dell'ultima modifica (fornito dal chiamante).
    """

    record_id: str
    content_hash: str
    updated_at: int


@dataclass(frozen=True)
class SyncPlan:
    """Piano di sincronizzazione fra manifest locale e remoto.

    Attributes:
        to_send: record_id che il locale deve inviare (assenti o più recenti).
        to_request: record_id che il locale deve richiedere (assenti o più recenti).
        conflicts: record_id con stesso updated_at ma hash diverso (da risolvere
            a livello applicativo; entrambi i record vanno conservati).
        in_sync: True se non c'è nulla da inviare, richiedere o risolvere.
    """

    to_send: tuple[str, ...]
    to_request: tuple[str, ...]
    conflicts: tuple[str, ...]
    in_sync: bool


def build_manifest(
    records: Iterable[tuple[str, bytes, int]],
) -> dict[str, RecordMeta]:
    """Costruisce un manifest da (record_id, payload, updated_at).

    Args:
        records: iterabile di tuple (record_id, payload bytes, updated_at epoch).

    Returns:
        Mapping record_id -> RecordMeta con content_hash = sha256(payload).
    """
    manifest: dict[str, RecordMeta] = {}
    for record_id, payload, updated_at in records:
        manifest[record_id] = RecordMeta(
            record_id=record_id,
            content_hash=hashlib.sha256(payload).hexdigest(),
            updated_at=updated_at,
        )
    return manifest


def _classify_record(lhs: RecordMeta | None, rhs: RecordMeta | None) -> str:
    """Classifica un record nel piano di sync: send | request | sync | conflict."""
    if lhs is not None and rhs is None:
        return "send"
    if rhs is not None and lhs is None:
        return "request"
    assert lhs is not None and rhs is not None
    if lhs.content_hash == rhs.content_hash:
        return "sync"
    if lhs.updated_at > rhs.updated_at:
        return "send"
    if rhs.updated_at > lhs.updated_at:
        return "request"
    return "conflict"


def diff_manifests(
    local: dict[str, RecordMeta],
    remote: dict[str, RecordMeta],
) -> SyncPlan:
    """Confronta manifest locale e remoto, applica Last-Write-Wins.

    Regole:
        - id solo locale, o locale più recente → to_send
        - id solo remoto, o remoto più recente → to_request
        - stesso id, stesso hash → in-sync (ignorato)
        - stesso id, hash diverso, stesso updated_at → conflicts (mai perdita)

    Args:
        local: manifest del peer locale.
        remote: manifest del peer remoto.

    Returns:
        SyncPlan deterministico (record_id ordinati).
    """
    to_send: list[str] = []
    to_request: list[str] = []
    conflicts: list[str] = []

    bucket = {"send": to_send, "request": to_request, "conflict": conflicts}
    for record_id in sorted(set(local) | set(remote)):
        kind = _classify_record(local.get(record_id), remote.get(record_id))
        if kind != "sync":
            bucket[kind].append(record_id)

    in_sync = not (to_send or to_request or conflicts)
    return SyncPlan(
        to_send=tuple(to_send),
        to_request=tuple(to_request),
        conflicts=tuple(conflicts),
        in_sync=in_sync,
    )
