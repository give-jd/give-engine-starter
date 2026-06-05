"""Session keyring in-memory: master key MAI persistita su disco.

Implementazione v0.1.0 Q3 W27 sprint alpha (1-7 lug 2026).
KAT scenarios: vedi `tests/kat/test_kat_keyring.py`.

Garanzie:
- Master key + derived key solo in RAM durante sessione.
- Auto-wipe su lock (auto_lock timeout) + atexit.
- Condiviso fra ricette nello stesso processo orchestrator.

Threat model:
- Cold boot attack RAM = OUT of scope (vedi CRYPTO-V0.1-SPEC.md §Threat model).
- Memory dump root-installed = OUT of scope.

Best-effort zero-fill: bytearray permette in-place modification. Python GC
e copy-on-write rendono wipe non garantito 100% (interpreter limitation).
"""

from __future__ import annotations

import atexit
import threading


class Keyring:
    """Session keyring in-memory.

    Storage: dict[str, bytearray]. bytearray (vs bytes) permette in-place
    zero-fill su wipe.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytearray] = {}
        self._lock = threading.RLock()

    def store(self, key_id: str, key_material: bytes) -> None:
        """Store key in keyring sessione.

        Args:
            key_id: identificatore opaco (UUID4 raccomandato).
            key_material: bytes materiale chiave (es. master key 32 byte).
        """
        if not isinstance(key_id, str) or not key_id:
            raise ValueError("key_id must be non-empty str")
        if not isinstance(key_material, (bytes, bytearray)):
            raise ValueError("key_material must be bytes")
        with self._lock:
            if key_id in self._store:
                self._zero_fill(self._store[key_id])
            self._store[key_id] = bytearray(key_material)

    def get(self, key_id: str) -> bytes | None:
        """Retrieve key da keyring.

        Returns:
            bytes copy del materiale (caller doesn't share keyring buffer),
            None altrimenti.
        """
        with self._lock:
            buf = self._store.get(key_id)
            if buf is None:
                return None
            return bytes(buf)

    def remove(self, key_id: str) -> None:
        """Rimuove key specifica + zero-fill memoria."""
        with self._lock:
            buf = self._store.pop(key_id, None)
            if buf is not None:
                self._zero_fill(buf)

    def wipe_all(self) -> None:
        """Zero-fill memoria + clear refs.

        Chiamato da:
        - auto_lock.AutoLockManager su timeout
        - atexit handler (registrato in get_keyring singleton)
        - explicit user lock action
        """
        with self._lock:
            for buf in self._store.values():
                self._zero_fill(buf)
            self._store.clear()

    @staticmethod
    def _zero_fill(buf: bytearray) -> None:
        """Best-effort zero-fill bytearray in place."""
        n = len(buf)
        for i in range(n):
            buf[i] = 0

    def __contains__(self, key_id: str) -> bool:
        with self._lock:
            return key_id in self._store

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# Singleton globale per processo orchestrator.
_GLOBAL_KEYRING: Keyring | None = None
_GLOBAL_LOCK = threading.Lock()


def get_keyring() -> Keyring:
    """Accessor singleton keyring globale.

    Pattern: 1 keyring per processo orchestrator. Condiviso fra ricette.
    Registra atexit hook per wipe_all alla chiusura processo.
    """
    global _GLOBAL_KEYRING
    if _GLOBAL_KEYRING is None:
        with _GLOBAL_LOCK:
            if _GLOBAL_KEYRING is None:
                kr = Keyring()
                atexit.register(kr.wipe_all)
                _GLOBAL_KEYRING = kr
    return _GLOBAL_KEYRING


def _reset_global_keyring_for_testing() -> None:
    """Reset singleton per test isolation (PRIVATO, no production use)."""
    global _GLOBAL_KEYRING
    with _GLOBAL_LOCK:
        if _GLOBAL_KEYRING is not None:
            _GLOBAL_KEYRING.wipe_all()
        _GLOBAL_KEYRING = None
