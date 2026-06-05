"""Envelope E2E per il trasferimento record fra peer LAN.

Ogni record viaggia cifrato AES-256-GCM (riuso `core.shared.crypto.aes_gcm`).
L'AAD lega `record_id|updated_at` all'auth tag: un peer ostile non può
rietichettare un record (cambiare id o timestamp nell'header) senza far
fallire la verifica di autenticità.

Il serializzato è JSON con campi binari in base64, trasportabile su qualsiasi
canale LAN. Nessuna chiave viaggia nell'envelope: i peer condividono la master
key fuori banda (è lo stesso utente sui propri dispositivi).
"""

from __future__ import annotations

import base64
import json

from core.shared.crypto.aes_gcm import EncryptedBlob, decrypt, encrypt
from core.shared.crypto.exceptions import CryptoError
from core.shared.sync.exceptions import SyncError

_ENVELOPE_VERSION = 1


def _aad(record_id: str, updated_at: int) -> bytes:
    """AAD canonica length-prefixed che lega id + timestamp al ciphertext.

    Frame non re-parsabile: 4-byte big-endian len(record_id_utf8) ||
    record_id_utf8 || 8-byte big-endian signed updated_at. Il prefisso di
    lunghezza elimina l'ambiguità del separatore: ("a|b", 1) e ("a", "b|1")
    producono AAD distinti, impedendo il relabeling MITM dei record.
    """
    rid = record_id.encode()
    return (
        len(rid).to_bytes(4, "big") + rid + updated_at.to_bytes(8, "big", signed=True)
    )


def seal_record(
    record_id: str,
    payload: bytes,
    updated_at: int,
    key: bytes,
) -> bytes:
    """Cifra un record in un envelope trasportabile.

    Args:
        record_id: identificatore del record (autenticato via AAD).
        payload: contenuto del record in bytes.
        updated_at: epoch seconds (autenticato via AAD).
        key: master key 32 byte condivisa fra i dispositivi dell'utente.

    Returns:
        Envelope JSON in bytes (campi binari base64).

    Raises:
        SyncError: se la cifratura fallisce (es. key length errata).
    """
    try:
        blob = encrypt(payload, key, aad=_aad(record_id, updated_at))
    except CryptoError as exc:
        raise SyncError(f"seal fallito: {exc}") from exc

    envelope = {
        "v": _ENVELOPE_VERSION,
        "record_id": record_id,
        "updated_at": updated_at,
        "nonce": base64.b64encode(blob.nonce).decode(),
        "auth_tag": base64.b64encode(blob.auth_tag).decode(),
        "ciphertext": base64.b64encode(blob.ciphertext).decode(),
    }
    return json.dumps(envelope).encode()


def open_record(envelope: bytes, key: bytes) -> tuple[str, bytes, int]:
    """Apre un envelope, verifica autenticità, restituisce il record.

    L'AAD è ricostruita da `record_id` + `updated_at` dell'header: se un peer
    ostile li ha alterati, la verifica GCM fallisce → SyncError.

    Args:
        envelope: bytes prodotti da `seal_record`.
        key: master key 32 byte (stessa usata in seal).

    Returns:
        (record_id, payload, updated_at).

    Raises:
        SyncError: envelope malformato, tampering, o chiave errata.
    """
    try:
        data = json.loads(envelope)
        record_id = data["record_id"]
        updated_at = data["updated_at"]
        # Valida i tipi dell'header PRIMA di ricostruire l'AAD: un updated_at
        # stringa (es. "b|1") o un bool romperebbe la canonicalizzazione e la
        # logica LWW a valle. bool è sottotipo di int → escluso esplicitamente.
        if (
            not isinstance(record_id, str)
            or not isinstance(updated_at, int)
            or isinstance(updated_at, bool)
        ):
            raise SyncError("envelope header con tipi invalidi")
        blob = EncryptedBlob(
            ciphertext=base64.b64decode(data["ciphertext"]),
            nonce=base64.b64decode(data["nonce"]),
            auth_tag=base64.b64decode(data["auth_tag"]),
            aad=_aad(record_id, updated_at),
        )
    except (KeyError, ValueError, OverflowError) as exc:
        raise SyncError(f"envelope malformato: {exc}") from exc

    try:
        payload = decrypt(blob, key)
    except CryptoError as exc:
        raise SyncError(
            "envelope non autentico (tampering, chiave errata o "
            f"record rietichettato): {exc}"
        ) from exc

    return record_id, payload, updated_at
