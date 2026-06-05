"""Auto-lock timeout + idle detection.

Skeleton interface v0.1.0-dev. Implementazione Q3 W28 (8-14 lug 2026).

Default timeouts:
- Catalogo standard: 1800s (30 min)
- Ricette art. 9 GDPR (cartella-clinica-light): 900s (15 min) override

Idle detection cross-platform:
- Linux: xprintidle / xidlehook (X11) o swayidle (Wayland)
- macOS: HIDIdleTime via Quartz
- Windows: GetLastInputInfo Win32 API
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


# Timeout standard Catalogo (30 min)
DEFAULT_TIMEOUT_SECONDS: int = 1800

# Timeout art. 9 GDPR ricette sensibili (15 min)
GDPR_ART9_TIMEOUT_SECONDS: int = 900


@dataclass
class AutoLockConfig:
    """Auto-lock configurabile per ricetta."""

    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    lock_on_idle: bool = True  # detect inactività mouse/keyboard
    lock_on_screensaver: bool = True


class AutoLockManager:
    """Gestione timeout cross-platform.

    Ricette categoria art. 9 GDPR override timeout a 900s (15 min).

    Implementation v0.1.0 Q3 W28 (timer-based; idle/screensaver detection
    rinviato a v0.2 — richiede platform-specific bindings).
    """

    def __init__(self) -> None:
        import threading

        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._config: AutoLockConfig | None = None
        self._on_lock: Callable[[], None] | None = None
        self._is_running: bool = False

    def start(self, config: AutoLockConfig, on_lock: Callable[[], None]) -> None:
        """Avvia timer.

        Args:
            config: AutoLockConfig (timeout + idle/screensaver flag).
            on_lock: callback chiamato su lock trigger.
        """
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        with self._lock:
            self._stop_timer_unlocked()
            self._config = config
            self._on_lock = on_lock
            self._is_running = True
            self._schedule_unlocked()

    def reset_timer(self) -> None:
        """Resetta timer (chiamato su user activity)."""
        with self._lock:
            if not self._is_running:
                return
            self._stop_timer_unlocked()
            self._schedule_unlocked()

    def stop(self) -> None:
        """Ferma timer cleanup."""
        with self._lock:
            self._is_running = False
            self._stop_timer_unlocked()

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def _schedule_unlocked(self) -> None:
        """Schedule nuovo timer (caller hold _lock)."""
        import threading

        if self._config is None or self._on_lock is None:
            return
        self._timer = threading.Timer(self._config.timeout_seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _stop_timer_unlocked(self) -> None:
        """Cancel timer (caller hold _lock)."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fire(self) -> None:
        """Timer callback: invoca on_lock + cleanup."""
        with self._lock:
            self._timer = None
            self._is_running = False
            cb = self._on_lock
            self._on_lock = None
            self._config = None
        if cb is not None:
            cb()
