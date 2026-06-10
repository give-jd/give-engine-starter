"""Test derivazione chiave handoff cross-persona."""
from __future__ import annotations

import pytest

from core.shared.handoff.exceptions import HandoffError
from core.shared.handoff.keys import HANDOFF_SALT_LEN, derive_handoff_key, genera_salt


def test_salt_lunghezza_corretta() -> None:
    salt = genera_salt()
    assert len(salt) == HANDOFF_SALT_LEN


def test_chiave_32_byte_deterministica() -> None:
    salt = b"\x00" * HANDOFF_SALT_LEN
    k1 = derive_handoff_key("correct horse battery", salt)
    k2 = derive_handoff_key("correct horse battery", salt)
    assert len(k1) == 32
    assert k1 == k2


def test_passphrase_diversa_chiave_diversa() -> None:
    salt = b"\x00" * HANDOFF_SALT_LEN
    assert derive_handoff_key("alpha", salt) != derive_handoff_key("beta", salt)


def test_salt_diverso_chiave_diversa() -> None:
    k1 = derive_handoff_key("alpha", b"\x00" * HANDOFF_SALT_LEN)
    k2 = derive_handoff_key("alpha", b"\x01" * HANDOFF_SALT_LEN)
    assert k1 != k2


def test_salt_invalido_solleva_handofferror() -> None:
    with pytest.raises(HandoffError):
        derive_handoff_key("alpha", b"")
