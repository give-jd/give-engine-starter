"""Derivazione chiave handoff da passphrase one-time condivisa fuori banda.

A differenza di crypto/argon2_kdf usato per il master password del singolo
utente, qui la chiave protegge un pacchetto scambiato fra DUE persone diverse
(cliente e professionista). Nessun segreto pre-condiviso: la passphrase
one-time viaggia su un canale separato dal pacchetto.
"""
from __future__ import annotations

import secrets

from core.shared.crypto.argon2_kdf import derive_key
from core.shared.crypto.exceptions import KeyDerivationError
from core.shared.handoff.exceptions import HandoffError

HANDOFF_SALT_LEN: int = 16


def genera_salt() -> bytes:
    """Salt random per pacchetto (persistito nel .gnp in chiaro, non segreto)."""
    return secrets.token_bytes(HANDOFF_SALT_LEN)


def derive_handoff_key(passphrase: str, salt: bytes) -> bytes:
    """Deriva chiave AES-GCM 32 byte da passphrase + salt via Argon2id.

    Args:
        passphrase: passphrase one-time comunicata fuori banda.
        salt: salt del pacchetto (16 byte).

    Returns:
        Chiave 32 byte per cifrare/decifrare gli envelope.

    Raises:
        HandoffError: se la derivazione Argon2id fallisce.
    """
    try:
        return derive_key(passphrase, salt)
    except KeyDerivationError as exc:
        raise HandoffError(f"derivazione chiave fallita: {exc}") from exc
