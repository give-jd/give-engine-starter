"""Test serializzazione e cifratura pacchetto .gnp."""
from __future__ import annotations

import pytest

from core.shared.handoff.exceptions import BadPackage, BadPassphrase
from core.shared.handoff.pack import pack, unpack

RECORDS = [
    {"record_id": "misurazione:1", "updated_at": 1717000000,
     "payload": {"data": "2026-06-01", "peso_kg": 72.5}},
    {"record_id": "pasto:1", "updated_at": 1717000100,
     "payload": {"data": "2026-06-01", "tipo": "pranzo", "kcal": 600}},
]


def test_roundtrip_preserva_record() -> None:
    blob = pack(RECORDS, "correct horse battery")
    out = unpack(blob, "correct horse battery")
    assert out == RECORDS


def test_passphrase_errata_solleva_badpassphrase() -> None:
    blob = pack(RECORDS, "giusta")
    with pytest.raises(BadPassphrase):
        unpack(blob, "sbagliata")


def test_magic_errato_solleva_badpackage() -> None:
    with pytest.raises(BadPackage):
        unpack(b"XXXX\x01rumore", "qualsiasi")


def test_tamper_ciphertext_solleva_badpassphrase() -> None:
    blob = bytearray(pack(RECORDS, "giusta"))
    blob[-1] ^= 0xFF
    with pytest.raises(BadPassphrase):
        unpack(bytes(blob), "giusta")


def test_pacchetto_vuoto() -> None:
    blob = pack([], "giusta")
    assert unpack(blob, "giusta") == []


def test_envelope_troncato_solleva_badpackage() -> None:
    blob = bytearray(pack(RECORDS, "giusta"))
    # tronca a metà dell'ultimo envelope: il length header rimane intatto ma
    # pos + ln > len(blob) → Fix A (BadPackage bounds-check, non open_record)
    truncated = bytes(blob[:-20])
    with pytest.raises(BadPackage):
        unpack(truncated, "giusta")


def test_byte_in_eccesso_solleva_badpackage() -> None:
    blob = pack(RECORDS, "giusta") + b"spazzatura"
    with pytest.raises(BadPackage):
        unpack(blob, "giusta")


def test_singolo_record_roundtrip() -> None:
    rec = [{"record_id": "misurazione:9", "updated_at": 5,
            "payload": {"data": "2026-06-01", "peso_kg": 80.0, "note": None}}]
    assert unpack(pack(rec, "k"), "k") == rec
