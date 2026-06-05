"""Cross-recipe OS notification (best-effort).

Backend priority: plyer (cross-platform) → native (osascript/notify-send/powershell).
Graceful degradation: se backend mancante, ritorna False senza eccezione.

Usage:
    from core.shared.notifier import notify_os
    notify_os("Bollo auto in scadenza", "Targa AB123CD entro 7 giorni")
"""

from __future__ import annotations

import platform
import shutil
import subprocess


def _notify_via_plyer(title: str, message: str) -> bool:
    try:
        from plyer import notification  # type: ignore
        notification.notify(title=title, message=message, timeout=10, app_name="Gi.Ve Engine")
        return True
    except Exception:
        return False


def _notify_macos(title: str, message: str) -> bool:
    if not shutil.which("osascript"):
        return False
    safe_msg = message.replace('"', "'")
    safe_title = title.replace('"', "'")
    script = f'display notification "{safe_msg}" with title "{safe_title}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5,
                       capture_output=True)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def _notify_linux(title: str, message: str) -> bool:
    if not shutil.which("notify-send"):
        return False
    try:
        subprocess.run(["notify-send", "-a", "Gi.Ve Engine", title, message],
                       check=True, timeout=5, capture_output=True)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def _notify_windows(title: str, message: str) -> bool:
    try:
        ps_script = (
            f'[Windows.UI.Notifications.ToastNotificationManager,'
            f'Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null; '
            f'$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; '
            f'$xml.LoadXml("<toast><visual><binding template=\\"ToastText02\\">'
            f'<text id=\\"1\\">{title}</text><text id=\\"2\\">{message}</text>'
            f'</binding></visual></toast>"); '
            f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier'
            f'("Gi.Ve Engine").Show([Windows.UI.Notifications.ToastNotification]::new($xml))'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script],
                       check=True, timeout=10, capture_output=True)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def notify_os(title: str, message: str) -> bool:
    """Best-effort OS notification. Returns True on success.

    Provider priority:
        1. plyer (se installato → uniform cross-platform)
        2. native: osascript (mac), notify-send (linux), powershell+toast (win)
        3. graceful False
    """
    if _notify_via_plyer(title, message):
        return True
    system = platform.system().lower()
    if system == "darwin":
        return _notify_macos(title, message)
    if system == "linux":
        return _notify_linux(title, message)
    if system == "windows":
        return _notify_windows(title, message)
    return False


def is_available() -> bool:
    """Check if any notification backend is available on this system."""
    try:
        import plyer  # noqa: F401
        return True
    except ImportError:
        pass
    system = platform.system().lower()
    if system == "darwin":
        return bool(shutil.which("osascript"))
    if system == "linux":
        return bool(shutil.which("notify-send"))
    if system == "windows":
        return bool(shutil.which("powershell"))
    return False
