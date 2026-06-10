"""Modulo handoff: scambio cifrato cross-persona via pacchetto .gnp."""
from core.shared.handoff.exceptions import (
    BadPackage,
    BadPassphrase,
    HandoffError,
)
from core.shared.handoff.keys import derive_handoff_key, genera_salt
from core.shared.handoff.pack import pack, unpack

__all__ = [
    "BadPackage",
    "BadPassphrase",
    "HandoffError",
    "derive_handoff_key",
    "genera_salt",
    "pack",
    "unpack",
]
