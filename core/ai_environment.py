"""Detect external AI tooling installed on the user's machine.

Surfaces a clear "what does the user already have / what would they need" so
the Cabina di Regia can show an honest, non-pushy onboarding card and the
/risorse-ia page can render the current environment.

NEVER logs or returns the actual ANTHROPIC_API_KEY value — only whether it
is present and where it was found. Detection has a hard wall-clock budget
of 5 seconds total; individual checks have their own bounded subprocess
timeouts; every check fails silently.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


GIVE_HOME = Path(os.environ.get("GIVE_HOME") or os.path.expanduser("~/.givengine"))
CACHE_FILE = GIVE_HOME / "ai_environment.json"

DETECTION_BUDGET_S = 5.0
SUBPROCESS_TIMEOUT_S = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _os_name() -> str:
    s = platform.system().lower()
    if s.startswith("darwin"):
        return "macos"
    if s.startswith("linux"):
        return "linux"
    if s.startswith("win"):
        return "windows"
    return s or "unknown"


def _safe_exists(*candidates):
    for c in candidates:
        if not c:
            continue
        try:
            p = Path(os.path.expandvars(os.path.expanduser(c)))
            if p.exists():
                return str(p)
        except (OSError, ValueError):
            continue
    return None


def _safe_which(binary):
    try:
        return shutil.which(binary)
    except Exception:
        return None


def _safe_version(cmd, budget_s=SUBPROCESS_TIMEOUT_S):
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=budget_s,
            check=False,
        )
        out = (res.stdout or res.stderr or "").strip()
        if not out:
            return None
        return out.splitlines()[0].strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, Exception):
        return None


def _registry_has(key, value_name=None):
    if _os_name() != "windows":
        return False
    try:
        import winreg  # type: ignore
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            if value_name is None:
                return True
            winreg.QueryValueEx(k, value_name)
            return True
    except OSError:
        return False


def _check_cursor():
    os_name = _os_name()
    path = None
    if os_name == "macos":
        path = _safe_exists("/Applications/Cursor.app",
                            "~/Applications/Cursor.app")
    elif os_name == "windows":
        # Cursor's official installer goes to %LOCALAPPDATA%\Programs\cursor,
        # but some users / IT-managed installs put it system-wide under
        # %PROGRAMFILES%, or via Scoop/Chocolatey/WinGet in their own dirs.
        path = _safe_exists(
            "%LOCALAPPDATA%\\Programs\\cursor\\Cursor.exe",
            "%LOCALAPPDATA%\\Programs\\Cursor\\Cursor.exe",
            "%APPDATA%\\Local\\Programs\\cursor\\Cursor.exe",
            "%PROGRAMFILES%\\Cursor\\Cursor.exe",
            "%PROGRAMFILES(X86)%\\Cursor\\Cursor.exe",
            "%PROGRAMFILES%\\cursor\\Cursor.exe",
            "%USERPROFILE%\\scoop\\apps\\cursor\\current\\Cursor.exe",
        )
        if not path and _registry_has(r"Software\Cursor"):
            path = "HKCU\\Software\\Cursor"
        if not path:
            # WinGet installs register in Uninstall key by ARP display name.
            for hive_key in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Cursor",
                             r"Software\Microsoft\Windows\CurrentVersion\Uninstall\cursor"):
                if _registry_has(hive_key):
                    path = "HKCU\\" + hive_key
                    break
    elif os_name == "linux":
        # Filesystem candidates: native /opt, snap, plus Flatpak app-ids both
        # system-wide and per-user. Anysphere historically published as
        # com.anysphere.cursor; community packages also exist under co.anysphere.Cursor.
        path = (_safe_which("cursor")
                or _safe_exists("/opt/Cursor",
                                "/opt/cursor",
                                "/snap/cursor/current",
                                "/var/lib/flatpak/app/com.anysphere.cursor",
                                "/var/lib/flatpak/app/com.cursor.Cursor",
                                "~/.local/share/flatpak/app/com.anysphere.cursor",
                                "~/.local/share/flatpak/app/com.cursor.Cursor",
                                "~/.local/share/applications/cursor.desktop",
                                "~/AppImages/Cursor.AppImage"))
    version = None
    if path and os_name == "linux" and shutil.which("cursor"):
        version = _safe_version(["cursor", "--version"], budget_s=1.0)
    return {"installed": bool(path), "path": path, "version": version}


def _check_windsurf():
    os_name = _os_name()
    path = None
    if os_name == "macos":
        path = _safe_exists("/Applications/Windsurf.app",
                            "~/Applications/Windsurf.app")
    elif os_name == "windows":
        path = _safe_exists(
            "%LOCALAPPDATA%\\Programs\\Windsurf\\Windsurf.exe",
            "%LOCALAPPDATA%\\Programs\\windsurf\\Windsurf.exe",
            "%PROGRAMFILES%\\Windsurf\\Windsurf.exe",
            "%PROGRAMFILES(X86)%\\Windsurf\\Windsurf.exe",
            "%USERPROFILE%\\scoop\\apps\\windsurf\\current\\Windsurf.exe",
        )
        if not path:
            for hive_key in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Windsurf",
                             r"Software\Microsoft\Windows\CurrentVersion\Uninstall\windsurf"):
                if _registry_has(hive_key):
                    path = "HKCU\\" + hive_key
                    break
    elif os_name == "linux":
        # Codeium ships Windsurf as com.codeium.windsurf (flatpak) plus a deb
        # that lands in /opt/windsurf. Some forks use lower-case names.
        path = (_safe_which("windsurf")
                or _safe_exists("/opt/Windsurf",
                                "/opt/windsurf",
                                "/snap/windsurf/current",
                                "/var/lib/flatpak/app/com.codeium.windsurf",
                                "/var/lib/flatpak/app/com.codeium.Windsurf",
                                "~/.local/share/flatpak/app/com.codeium.windsurf",
                                "~/.local/share/flatpak/app/com.codeium.Windsurf",
                                "~/.local/share/applications/windsurf.desktop"))
    version = None
    if path and os_name == "linux" and shutil.which("windsurf"):
        version = _safe_version(["windsurf", "--version"], budget_s=1.0)
    return {"installed": bool(path), "path": path, "version": version}


def _check_claude_code():
    bin_path = _safe_which("claude")
    version = None
    if bin_path:
        version = _safe_version([bin_path, "--version"], budget_s=2.0)
    return {"installed": bool(bin_path), "path": bin_path, "version": version}


def _check_vscode():
    os_name = _os_name()
    path = None
    if os_name == "macos":
        path = _safe_exists("/Applications/Visual Studio Code.app",
                            "~/Applications/Visual Studio Code.app",
                            "/Applications/VSCodium.app")
    elif os_name == "windows":
        path = _safe_exists(
            "%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe",
            "%PROGRAMFILES%\\Microsoft VS Code\\Code.exe",
            "%PROGRAMFILES(X86)%\\Microsoft VS Code\\Code.exe",
            "%USERPROFILE%\\scoop\\apps\\vscode\\current\\Code.exe",
        )
    elif os_name == "linux":
        path = (_safe_which("code")
                or _safe_which("codium")
                or _safe_exists("/snap/code/current",
                                "/usr/share/code/code",
                                "/opt/visual-studio-code",
                                "/var/lib/flatpak/app/com.visualstudio.code",
                                "/var/lib/flatpak/app/com.vscodium.codium",
                                "~/.local/share/flatpak/app/com.visualstudio.code"))
    return {"installed": bool(path), "path": path, "version": None}


def _check_anthropic_key():
    """NEVER returns the value, only presence + source.

    Priority is givengine creds → anthropic SDK creds file → ANTHROPIC_API_KEY
    env var. The env var is the most common source in CI / dev shells, the
    SDK creds file is what `anthropic login` writes, and the givengine
    creds file is the path we'll write to once BYOK lands in the UI.

    Path resolution per platform:
    - POSIX (macOS/Linux): `~/.anthropic/credentials`
      → `/Users/<u>/.anthropic/credentials` or `/home/<u>/.anthropic/credentials`
    - Windows: `~/.anthropic/credentials`
      → `os.path.expanduser` resolves `~` to `%USERPROFILE%`, so we get
        `C:\\Users\\<u>\\.anthropic\\credentials`. This works natively
        on every Python ≥ 3.5 — no extra Windows-specific logic needed.
        Same goes for `GIVE_HOME` (`~/.givengine`).
    """
    creds_file = GIVE_HOME / "credentials.json"
    try:
        if creds_file.exists():
            data = json.loads(creds_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("anthropic_api_key"):
                return {"configured": True, "source": "givengine"}
    except (json.JSONDecodeError, OSError):
        pass

    sdk_file = Path(os.path.expanduser("~/.anthropic/credentials"))
    try:
        if sdk_file.exists() and sdk_file.stat().st_size > 0:
            return {"configured": True, "source": "anthropic_sdk"}
    except OSError:
        pass

    env_val = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_val:
        return {"configured": True, "source": "env"}

    return {"configured": False, "source": None}


def _summarize(cursor, windsurf, claude_code, vscode):
    has_any_ide_ai = bool(cursor["installed"] or windsurf["installed"]
                          or claude_code["installed"])
    if has_any_ide_ai:
        level = "ready"
    elif vscode["installed"]:
        level = "partial"
    else:
        level = "missing"
    return {
        "has_any_ide_ai": has_any_ide_ai,
        "recommendation_level": level,
    }


class AIEnvironmentDetector:
    def __init__(self, cache_file=CACHE_FILE, budget_s=DETECTION_BUDGET_S):
        self.cache_file = Path(cache_file)
        self.budget_s = budget_s

    def load_cached(self):
        if not self.cache_file.exists():
            return None
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def cache_is_fresh(self, max_age_s=86400.0):
        data = self.load_cached()
        if not data:
            return False
        ts = data.get("last_check_at")
        if not ts:
            return False
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return False
        return (datetime.now(timezone.utc) - t).total_seconds() < max_age_s

    def _save(self, payload):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def check(self):
        start = time.monotonic()

        def remaining():
            return self.budget_s - (time.monotonic() - start)

        empty_check = {"installed": False, "path": None, "version": None}

        def run(fn, default):
            if remaining() <= 0:
                return default
            try:
                return fn()
            except Exception:
                return default

        cursor      = run(_check_cursor,        empty_check)
        windsurf    = run(_check_windsurf,      empty_check)
        claude_code = run(_check_claude_code,   empty_check)
        vscode      = run(_check_vscode,        empty_check)
        api_key     = run(_check_anthropic_key, {"configured": False, "source": None})

        payload = {
            "last_check_at": _now_iso(),
            "platform": _os_name(),
            "cursor": cursor,
            "windsurf": windsurf,
            "claude_code": claude_code,
            "vscode": vscode,
            "anthropic_api_key": api_key,
            "summary": _summarize(cursor, windsurf, claude_code, vscode),
        }
        try:
            self._save(payload)
        except Exception:
            pass
        return payload

    def refresh(self):
        return self.check()

    def status(self):
        cached = self.load_cached()
        if cached:
            return cached
        return self.check()


_singleton: Optional[AIEnvironmentDetector] = None


def detector():
    global _singleton
    if _singleton is None:
        _singleton = AIEnvironmentDetector()
    return _singleton


if __name__ == "__main__":
    print(json.dumps(AIEnvironmentDetector().check(), indent=2, ensure_ascii=False))
