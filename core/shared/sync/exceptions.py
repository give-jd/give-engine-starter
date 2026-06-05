"""Exception hierarchy del modulo sync.

Tutti gli errori del modulo derivano da `SyncError` così i chiamanti
catturano l'intera superficie con un singolo except.
"""

from __future__ import annotations


class SyncError(Exception):
    """Errore del modulo sync (envelope tamper, host non-LAN, manifest malformato)."""
