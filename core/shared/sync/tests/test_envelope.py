"""Tests per envelope E2E (roundtrip, tamper, anti-swap)."""

from __future__ import annotations

import base64
import json

import pytest

from core.shared.sync.envelope import open_record, seal_record
from core.shared.sync.exceptions import SyncError

_KEY = b"\x01" * 32
_OTHER_KEY = b"\x02" * 32


def test_roundtrip():
    env = seal_record("r1", b"payload segreto", 1234, _KEY)
    rid, payload, ts = open_record(env, _KEY)
    assert rid == "r1"
    assert payload == b"payload segreto"
    assert ts == 1234


def test_roundtrip_empty_payload():
    env = seal_record("r1", b"", 1, _KEY)
    _, payload, _ = open_record(env, _KEY)
    assert payload == b""


def test_wrong_key_fails():
    env = seal_record("r1", b"x", 1, _KEY)
    with pytest.raises(SyncError):
        open_record(env, _OTHER_KEY)


def test_tampered_ciphertext_fails():
    env = seal_record("r1", b"originale", 1, _KEY)
    data = json.loads(env)
    # flip un byte del ciphertext
    ct = bytearray(base64.b64decode(data["ciphertext"]))
    ct[0] ^= 0xFF
    data["ciphertext"] = base64.b64encode(bytes(ct)).decode()
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)


def test_anti_swap_record_id_fails():
    # peer ostile cambia record_id nell'header → AAD non combacia → auth fail
    env = seal_record("r1", b"x", 1, _KEY)
    data = json.loads(env)
    data["record_id"] = "r2"
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)


def test_anti_swap_updated_at_fails():
    env = seal_record("r1", b"x", 100, _KEY)
    data = json.loads(env)
    data["updated_at"] = 999
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)


def test_malformed_envelope_fails():
    with pytest.raises(SyncError):
        open_record(b"non-json", _KEY)


def test_missing_field_fails():
    with pytest.raises(SyncError):
        open_record(json.dumps({"record_id": "r1"}).encode(), _KEY)


def test_seal_bad_key_length_raises():
    with pytest.raises(SyncError):
        seal_record("r1", b"x", 1, b"short")


def test_header_updated_at_string_type_rejected():
    # int updated_at sigillato; header riscritto a stringa "1" → rifiutato
    env = seal_record("r1", b"x", 1, _KEY)
    data = json.loads(env)
    data["updated_at"] = "1"
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)


def test_header_updated_at_bool_rejected():
    env = seal_record("r1", b"x", 1, _KEY)
    data = json.loads(env)
    data["updated_at"] = True  # bool è sottotipo di int → deve essere rifiutato
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)


def test_header_record_id_nonstring_rejected():
    env = seal_record("r1", b"x", 1, _KEY)
    data = json.loads(env)
    data["record_id"] = 123
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)


def test_no_separator_ambiguity_relabeling_blocked():
    # ("a|b", 1) non deve poter essere reinterpretato come ("a", "b|1").
    # Con AAD length-prefixed il tentativo fallisce sia per tipo (updated_at
    # stringa) sia, ipoteticamente, per AAD diverso.
    env = seal_record("a|b", b"segreto", 1, _KEY)
    data = json.loads(env)
    data["record_id"] = "a"
    data["updated_at"] = "b|1"
    with pytest.raises(SyncError):
        open_record(json.dumps(data).encode(), _KEY)
    # round-trip legittimo resta valido
    rid, payload, ts = open_record(env, _KEY)
    assert rid == "a|b" and payload == b"segreto" and ts == 1
