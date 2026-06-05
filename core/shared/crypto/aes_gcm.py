"""AES-256-GCM encrypt/decrypt + auth tag.

Implementazione v0.1.0 Q3 W27 sprint alpha (1-7 lug 2026).
Backend: PyCA `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
KAT vectors: vedi `tests/kat/test_kat_aes_gcm.py`.

Riferimenti standard:
- RFC 5116 An Interface and Algorithms for Authenticated Encryption
- NIST SP 800-38D Recommendation for Block Cipher Modes (GCM)
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.shared.crypto.exceptions import AuthFailed, CryptoError


# Costanti standard AES-GCM (NIST raccomandato)
NONCE_LEN_BYTES: int = 12  # 96-bit nonce raccomandato GCM
AUTH_TAG_LEN_BYTES: int = 16  # 128-bit tag
KEY_LEN_BYTES: int = 32  # AES-256


@dataclass(frozen=True)
class EncryptedBlob:
    """Blob cifrato AES-256-GCM.

    Format autocontained: ciphertext + nonce + auth_tag + AAD opzionale.
    Tutti i field sono required per decrypt + auth verify.
    """

    ciphertext: bytes
    nonce: bytes  # 12 byte NIST raccomandato
    auth_tag: bytes  # 16 byte
    aad: bytes | None  # additional authenticated data opzionale


def _validate_key(key: bytes) -> None:
    if not isinstance(key, (bytes, bytearray)):
        raise CryptoError(f"Key must be bytes, got {type(key).__name__}")
    if len(key) != KEY_LEN_BYTES:
        raise CryptoError(
            f"Key length must be {KEY_LEN_BYTES} byte (AES-256), got {len(key)}"
        )


def encrypt(
    plaintext: bytes,
    key: bytes,
    aad: bytes | None = None,
    *,
    _nonce_for_testing: bytes | None = None,
) -> EncryptedBlob:
    """Cifra plaintext con AES-256-GCM.

    Args:
        plaintext: bytes da cifrare (può essere vuoto).
        key: 32 byte master key (AES-256).
        aad: additional authenticated data opzionale. Autenticato ma non cifrato.
        _nonce_for_testing: override nonce per KAT (PRIVATO, no production use).

    Returns:
        EncryptedBlob con ciphertext + nonce random + auth_tag + AAD.

    Raises:
        CryptoError: se key length != 32 byte o input invalido.
    """
    _validate_key(key)

    if _nonce_for_testing is not None:
        if len(_nonce_for_testing) != NONCE_LEN_BYTES:
            raise CryptoError(
                f"Nonce length must be {NONCE_LEN_BYTES} byte, "
                f"got {len(_nonce_for_testing)}"
            )
        nonce = bytes(_nonce_for_testing)
    else:
        nonce = secrets.token_bytes(NONCE_LEN_BYTES)

    aesgcm = AESGCM(bytes(key))
    # PyCA AESGCM.encrypt returns ciphertext || auth_tag concatenated.
    ct_and_tag = aesgcm.encrypt(nonce, bytes(plaintext), aad)
    ciphertext = ct_and_tag[:-AUTH_TAG_LEN_BYTES]
    auth_tag = ct_and_tag[-AUTH_TAG_LEN_BYTES:]

    return EncryptedBlob(
        ciphertext=ciphertext,
        nonce=nonce,
        auth_tag=auth_tag,
        aad=aad,
    )


def decrypt(blob: EncryptedBlob, key: bytes) -> bytes:
    """Decifra blob AES-256-GCM e verifica auth tag.

    Args:
        blob: EncryptedBlob da decifrare.
        key: 32 byte master key (deve essere uguale alla key usata in encrypt).

    Returns:
        plaintext bytes originali.

    Raises:
        AuthFailed: se auth tag non verifica (key sbagliata o tamper detected).
        CryptoError: se key length invalida o blob malformato.
    """
    _validate_key(key)
    if len(blob.nonce) != NONCE_LEN_BYTES:
        raise CryptoError(f"Invalid nonce length: {len(blob.nonce)}")
    if len(blob.auth_tag) != AUTH_TAG_LEN_BYTES:
        raise CryptoError(f"Invalid auth tag length: {len(blob.auth_tag)}")

    aesgcm = AESGCM(bytes(key))
    ct_and_tag = blob.ciphertext + blob.auth_tag
    try:
        plaintext = aesgcm.decrypt(blob.nonce, ct_and_tag, blob.aad)
    except InvalidTag as exc:
        raise AuthFailed(
            "AES-GCM auth tag verification failed (wrong key or tampered data)"
        ) from exc
    return plaintext
