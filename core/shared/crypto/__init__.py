"""Modulo `core/shared/crypto/` v0.1 — cifratura at-rest + master password + recovery.

API pubbliche:
- encrypt/decrypt (AES-256-GCM) → `aes_gcm`
- derive_key (Argon2id KDF) → `argon2_kdf`
- setup/unlock/change_password/reset_with_recovery → `master_password`
- generate_recovery_phrase/verify_phrase → `recovery_bip39`
- Keyring sessione (in-memory, auto-wipe) → `keyring`
- AutoLockManager → `auto_lock`

Spec autoritativa: `givegroup-knowledge/shared/CRYPTO-V0.1-SPEC.md`
KAT design: `givegroup-knowledge/shared/CRYPTO-V0.1-KAT-DESIGN.md`
Roadmap sviluppo: `givegroup-knowledge/give-engine/ROADMAP-Q3-2026.md`

Stato: v0.1.0-dev skeleton (Pre-Q3 W4-W5). Implementazione full Q3 W27-W29
(1-21 lug 2026). Tag stable `crypto-v0.1.0` target W29.
"""

from __future__ import annotations

from pathlib import Path

# Versione modulo (semver). Sync con file CRYPTO_VERSION.
_VERSION_FILE = Path(__file__).parent / "CRYPTO_VERSION"
__version__ = _VERSION_FILE.read_text(encoding="utf-8").strip()

# Re-export public API (eccezioni)
# noqa: E402 — version lookup tramite file CRYPTO_VERSION precede re-exports
from core.shared.crypto.exceptions import (  # noqa: E402
    AlreadyInitialized,
    AuthFailed,
    ConfigCorrupted,
    CryptoError,
    EmptyPassword,
    InvalidRecovery,
    KeyDerivationError,
    NotInitialized,
    WeakPassword,
)

__all__ = [
    "__version__",
    "AlreadyInitialized",
    "AuthFailed",
    "ConfigCorrupted",
    "CryptoError",
    "EmptyPassword",
    "InvalidRecovery",
    "KeyDerivationError",
    "NotInitialized",
    "WeakPassword",
]
