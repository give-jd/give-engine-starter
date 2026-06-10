"""Eccezioni del modulo handoff (scambio cifrato cross-persona)."""
from __future__ import annotations


class HandoffError(Exception):
    """Errore base del modulo handoff."""


class BadPassphrase(HandoffError):
    """Passphrase errata: la decifratura non autentica."""


class BadPackage(HandoffError):
    """Pacchetto malformato, versione ignota o magic errato."""
