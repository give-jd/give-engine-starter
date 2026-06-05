"""Argon2id KDF master password → master key.

Implementazione v0.1.0 Q3 W27 sprint alpha (1-7 lug 2026).
Backend: argon2-cffi `argon2.low_level.hash_secret_raw`.
KAT vectors: vedi `tests/kat/test_kat_argon2id.py`.

Riferimenti standard:
- RFC 9106 Argon2 Memory-Hard Function for Password Hashing
- OWASP 2026 Password Storage Cheat Sheet raccomandazioni
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from argon2 import low_level as _argon2_low
from argon2.exceptions import Argon2Error

from core.shared.crypto.exceptions import KeyDerivationError


# OWASP 2026 raccomandazione Argon2id
DEFAULT_TIME_COST: int = 3
DEFAULT_MEMORY_COST_KB: int = 65_536  # 64 MB
DEFAULT_PARALLELISM: int = 4
DEFAULT_OUTPUT_LEN: int = 32  # 32 byte master key

# Salt length standard
SALT_LEN_BYTES: int = 16


@dataclass(frozen=True)
class Argon2Params:
    """Argon2id parameters. Default OWASP 2026 raccomandazione."""

    time_cost: int = DEFAULT_TIME_COST  # iterazioni
    memory_cost_kb: int = DEFAULT_MEMORY_COST_KB  # 64 MB
    parallelism: int = DEFAULT_PARALLELISM
    output_len: int = DEFAULT_OUTPUT_LEN  # 32 byte


DEFAULT_PARAMS = Argon2Params()


def derive_key(
    password: str,
    salt: bytes,
    params: Argon2Params = DEFAULT_PARAMS,
) -> bytes:
    """Deriva master key da password + salt via Argon2id.

    Args:
        password: master password utente (UTF-8 string).
        salt: 16 byte salt random per setup, persistito.
        params: parametri Argon2id (default OWASP 2026).

    Returns:
        Master key bytes (params.output_len, default 32 byte).

    Raises:
        KeyDerivationError: se Argon2id internal fail (params invalidi, OOM).

    Performance target: ~250ms su CPU mainstream (Intel i5 2026 / Apple M2).
    """
    return derive_key_raw(
        password=password.encode("utf-8"),
        salt=salt,
        params=params,
    )


def derive_key_raw(
    password: bytes,
    salt: bytes,
    secret: bytes = b"",  # NOSONAR
    ad: bytes = b"",  # NOSONAR
    params: Argon2Params = DEFAULT_PARAMS,
) -> bytes:
    """Variante raw bytes (per KAT con RFC 9106 vector full).

    Args:
        password: bytes password.
        salt: salt bytes (min 8 byte RFC 9106).
        secret: optional pepper (riservato — argon2-cffi low-level non lo espone).
        ad: associated data (riservato — argon2-cffi low-level non lo espone).
        params: Argon2id parameters.

    Returns:
        Hash bytes (params.output_len).

    Raises:
        KeyDerivationError: se argon2-cffi rejects params o internal fail.
    """
    try:
        return _argon2_low.hash_secret_raw(
            secret=bytes(password),
            salt=bytes(salt),
            time_cost=params.time_cost,
            memory_cost=params.memory_cost_kb,
            parallelism=params.parallelism,
            hash_len=params.output_len,
            type=_argon2_low.Type.ID,
            version=_argon2_low.ARGON2_VERSION,
        )
    except Argon2Error as exc:
        raise KeyDerivationError(f"Argon2id derivation failed: {exc}") from exc


def generate_salt() -> bytes:
    """Genera 16 byte salt random per nuovo setup.

    Returns:
        16 byte cryptographically secure random.
    """
    return secrets.token_bytes(SALT_LEN_BYTES)
