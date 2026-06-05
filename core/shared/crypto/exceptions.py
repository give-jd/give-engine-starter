"""Eccezioni modulo crypto v0.1.

Gerarchia:
- CryptoError (base)
  - AuthFailed (auth tag invalido o password sbagliata)
  - KeyDerivationError (Argon2id failed)
  - InvalidRecovery (recovery phrase invalida o checksum failed)
  - EmptyPassword (setup con password vuota)
  - WeakPassword (warning, non-fatale)
  - NotInitialized (unlock prima setup)
  - AlreadyInitialized (setup duplicato)
  - ConfigCorrupted (salt/magic/params corrotti)
"""

from __future__ import annotations


class CryptoError(Exception):
    """Base exception modulo crypto."""


class AuthFailed(CryptoError):
    """Authentication failed: auth tag invalido o password sbagliata.

    Sollevato da:
    - aes_gcm.decrypt se auth tag non verifica (tamper detection)
    - master_password.unlock se password sbagliata
    - master_password.change_password se vecchia password sbagliata
    """


class KeyDerivationError(CryptoError):
    """Argon2id KDF failed (params invalidi o internal error)."""


class InvalidRecovery(CryptoError):
    """Recovery phrase invalida: checksum failed o parole non in wordlist."""


class EmptyPassword(CryptoError):
    """Setup con password vuota: rifiutato per default conservativo."""


class WeakPassword(Warning):
    """Password debole (< 12 char). Warning non-fatale.

    Setup procede ma utente avvisato. Coerente Punto 15 (default conservativo).
    """


class NotInitialized(CryptoError):
    """Unlock chiamato prima di setup: nessun salt/params persistiti."""


class AlreadyInitialized(CryptoError):
    """Setup chiamato due volte: config esistente non sovrascritto.

    Per re-setup, utente deve esplicitamente cancellare config file +
    confermare perdita dati cifrati esistenti.
    """


class ConfigCorrupted(CryptoError):
    """File config corrotto: salt/magic/params non parseable o tampered."""
