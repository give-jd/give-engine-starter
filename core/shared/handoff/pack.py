"""Serializzazione pacchetto .gnp (Give Nutrition Package).

Formato binario:
    magic    b"GNP1"          4 byte
    version  uint8            1 byte (=1)
    salt     16 byte          Argon2 salt random per pacchetto
    n        uint16 big       numero record
    records  n × [uint32 big len | envelope]   envelope = sync.envelope.seal_record

Ogni record è un dict {"record_id": str, "updated_at": int, "payload": <json>}.
Il payload viene serializzato JSON, sigillato in un envelope AES-GCM con AAD
(record_id+updated_at). Passphrase errata o tamper → la GCM non autentica →
BadPassphrase.

Nota: il payload deve essere JSON-native (chiavi stringa; no tuple/complex).
"""
from __future__ import annotations

import json
import struct
from typing import Any

from core.shared.sync.envelope import open_record, seal_record
from core.shared.sync.exceptions import SyncError

from core.shared.handoff.exceptions import BadPackage, BadPassphrase, HandoffError
from core.shared.handoff.keys import (
    HANDOFF_SALT_LEN,
    derive_handoff_key,
    genera_salt,
)

_MAGIC = b"GNP1"
_VERSION = 1


def pack(records: list[dict[str, Any]], passphrase: str) -> bytes:
    """Serializza e cifra i record in un pacchetto .gnp.

    Args:
        records: lista di {"record_id": str, "updated_at": int, "payload": json}.
        passphrase: passphrase one-time (comunicata fuori banda al destinatario).

    Returns:
        Bytes del pacchetto .gnp.
    """
    if len(records) > 0xFFFF:
        raise HandoffError(f"troppi record: massimo 65535, ricevuti {len(records)}")
    salt = genera_salt()
    key = derive_handoff_key(passphrase, salt)
    out = bytearray()
    out += _MAGIC
    out += struct.pack("!B", _VERSION)
    out += salt
    out += struct.pack("!H", len(records))
    for rec in records:
        payload = json.dumps(rec["payload"]).encode("utf-8")
        envelope = seal_record(rec["record_id"], payload, rec["updated_at"], key)
        out += struct.pack("!I", len(envelope))
        out += envelope
    return bytes(out)


def unpack(blob: bytes, passphrase: str) -> list[dict[str, Any]]:
    """Decifra un pacchetto .gnp e restituisce i record.

    Args:
        blob: bytes prodotti da pack().
        passphrase: passphrase one-time ricevuta fuori banda.

    Returns:
        Lista di record nello stesso formato passato a pack().

    Raises:
        BadPackage: magic/versione errati o pacchetto troncato.
        BadPassphrase: passphrase errata o pacchetto manomesso.
    """
    try:
        if blob[:4] != _MAGIC:
            raise BadPackage("magic non valido: non è un pacchetto .gnp")
        version = struct.unpack("!B", blob[4:5])[0]
        if version != _VERSION:
            raise BadPackage(f"versione pacchetto non supportata: {version}")
        salt = blob[5 : 5 + HANDOFF_SALT_LEN]
        if len(salt) != HANDOFF_SALT_LEN:
            raise BadPackage(f"salt troncato: {len(salt)}/{HANDOFF_SALT_LEN} byte")
        pos = 5 + HANDOFF_SALT_LEN
        (n,) = struct.unpack("!H", blob[pos : pos + 2])
        pos += 2
    except (IndexError, struct.error) as exc:
        raise BadPackage(f"pacchetto troncato o malformato: {exc}") from exc

    key = derive_handoff_key(passphrase, salt)
    records: list[dict[str, Any]] = []
    for _ in range(n):
        try:
            (ln,) = struct.unpack("!I", blob[pos : pos + 4])
            pos += 4
        except (IndexError, struct.error) as exc:
            raise BadPackage(f"record troncato: {exc}") from exc
        if pos + ln > len(blob):
            raise BadPackage(
                f"record troncato: annunciati {ln} byte, disponibili {len(blob) - pos}"
            )
        envelope = blob[pos : pos + ln]
        pos += ln
        try:
            record_id, payload, updated_at = open_record(envelope, key)
        except SyncError as exc:
            raise BadPassphrase("passphrase errata o pacchetto corrotto") from exc
        records.append(
            {
                "record_id": record_id,
                "updated_at": updated_at,
                "payload": json.loads(payload),
            }
        )
    if pos != len(blob):
        raise BadPackage(f"byte in eccesso dopo l'ultimo record: {len(blob) - pos}")
    return records
