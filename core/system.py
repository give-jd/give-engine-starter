"""OS-level helpers for the Cabina di Regia: first-launch flag, auto-start
toggle, preferences persistence.

The same three operating systems supported by installer/install.{sh,ps1}
are mirrored here so the UI can flip auto-start at runtime without
re-running the installer.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


GIVE_HOME = Path(os.environ.get("GIVE_HOME") or os.path.expanduser("~/.givengine"))
PREFS_FILE = GIVE_HOME / "preferences.json"
FIRST_LAUNCH_MARKER = GIVE_HOME / ".first_launch_done"


def os_name() -> str:
    s = platform.system().lower()
    if s.startswith("darwin"):
        return "macos"
    if s.startswith("linux"):
        return "linux"
    if s.startswith("win"):
        return "windows"
    return s or "unknown"


def os_label() -> str:
    return {"macos": "Mac", "linux": "Linux", "windows": "Windows"}.get(os_name(), os_name())


def shortcut_location_label() -> str:
    return {
        "macos":   "Dock (cartella Applicazioni)",
        "linux":   "Menu delle Applicazioni",
        "windows": "Desktop e Menu Start",
    }.get(os_name(), "Menu delle Applicazioni")


def _load_prefs() -> dict:
    if not PREFS_FILE.exists():
        return {}
    try:
        return json.loads(PREFS_FILE.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_prefs(data: dict) -> None:
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_pref(key: str, default=None):
    return _load_prefs().get(key, default)


def set_pref(key: str, value) -> None:
    data = _load_prefs()
    data[key] = value
    _save_prefs(data)


def is_first_launch() -> bool:
    return not FIRST_LAUNCH_MARKER.exists()


def mark_first_launch_done() -> None:
    FIRST_LAUNCH_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FIRST_LAUNCH_MARKER.touch(exist_ok=True)


def _venv_python() -> str:
    if sys.platform.startswith("win"):
        candidate = GIVE_HOME / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = GIVE_HOME / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _venv_pythonw_win() -> str:
    candidate = GIVE_HOME / ".venv" / "Scripts" / "pythonw.exe"
    if candidate.exists():
        return str(candidate)
    return _venv_python()


def autostart_is_enabled() -> bool:
    """Inspect the OS-level mechanism (single source of truth)."""
    name = os_name()
    if name == "macos":
        plist = Path(os.path.expanduser("~/Library/LaunchAgents/it.givegroup.engine.plist"))
        return plist.exists()
    if name == "linux":
        desk = Path(os.path.expanduser("~/.config/autostart/givengine.desktop"))
        return desk.exists()
    if name == "windows":
        try:
            import winreg  # type: ignore
        except ImportError:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "Gi.Ve Engine")
                return True
        except OSError:
            return False
    return False


def enable_autostart() -> tuple:
    name = os_name()
    try:
        if name == "macos":
            _enable_autostart_macos()
        elif name == "linux":
            _enable_autostart_linux()
        elif name == "windows":
            _enable_autostart_windows()
        else:
            return False, f"Auto-start non supportato su {name}."
    except Exception as e:
        return False, f"Errore durante l'attivazione: {e}"
    set_pref("autostart", True)
    return True, "Auto-start attivato. Gi.Ve Engine partirà a ogni accensione."


def disable_autostart() -> tuple:
    name = os_name()
    try:
        if name == "macos":
            _disable_autostart_macos()
        elif name == "linux":
            _disable_autostart_linux()
        elif name == "windows":
            _disable_autostart_windows()
        else:
            return False, f"Auto-start non supportato su {name}."
    except Exception as e:
        return False, f"Errore durante la disattivazione: {e}"
    set_pref("autostart", False)
    return True, "Auto-start disattivato."


_SHELL_MARK_START = "# >>> Gi.Ve Engine autostart >>>"
_SHELL_MARK_END = "# <<< Gi.Ve Engine autostart <<<"


def _bash_profile_path() -> Path:
    return Path(os.path.expanduser("~/.bash_profile"))


def shell_autostart_line() -> str:
    """Blocco (con marker) che avvia l'orchestrator al login di shell.

    Idempotente all'esecuzione: non riavvia se l'orchestrator gira già.
    """
    py = _venv_python()
    home = str(GIVE_HOME)
    body = (
        'pgrep -f "core.orchestrator" >/dev/null 2>&1 || '
        f'( cd "{home}" && nohup "{py}" -m core.orchestrator --no-browser '
        ">/dev/null 2>&1 & )"
    )
    return f"{_SHELL_MARK_START}\n{body}\n{_SHELL_MARK_END}\n"


def shell_autostart_is_enabled() -> bool:
    p = _bash_profile_path()
    if not p.exists():
        return False
    return _SHELL_MARK_START in p.read_text(encoding="utf-8", errors="ignore")


def enable_autostart_shell() -> tuple:
    """Append idempotente del blocco di autostart a ~/.bash_profile."""
    if os_name() == "windows":
        return False, "Il bash profile non esiste su Windows. Usa l'avvio automatico standard."
    p = _bash_profile_path()
    try:
        existing = p.read_text(encoding="utf-8") if p.exists() else ""
        if _SHELL_MARK_START in existing:
            return True, f"Avvio da bash profile già presente in {p}."
        prefix = "\n" if existing and not existing.endswith("\n") else ""
        with p.open("a", encoding="utf-8") as fh:
            fh.write(prefix + shell_autostart_line())
        return True, f"Aggiunto a {p}. Parte al prossimo login del terminale."
    except OSError as e:
        return False, f"Errore scrittura {p}: {e}"


def disable_autostart_shell() -> tuple:
    """Rimuove il blocco marcato da ~/.bash_profile (lascia il resto intatto)."""
    p = _bash_profile_path()
    if not p.exists():
        return True, "Niente da rimuovere."
    try:
        out, skip = [], False
        for ln in p.read_text(encoding="utf-8").splitlines(keepends=True):
            stripped = ln.strip()
            if stripped == _SHELL_MARK_START:
                skip = True
                continue
            if stripped == _SHELL_MARK_END:
                skip = False
                continue
            if not skip:
                out.append(ln)
        p.write_text("".join(out), encoding="utf-8")
        return True, "Avvio da bash profile rimosso."
    except OSError as e:
        return False, f"Errore: {e}"


def _enable_autostart_macos() -> None:
    plist_dir = Path(os.path.expanduser("~/Library/LaunchAgents"))
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / "it.givegroup.engine.plist"
    logs = GIVE_HOME / "core" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>it.givegroup.engine</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_venv_python()}</string>
    <string>-m</string>
    <string>core.orchestrator</string>
  </array>
  <key>WorkingDirectory</key><string>{GIVE_HOME}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>{logs}/engine.out</string>
  <key>StandardErrorPath</key><string>{logs}/engine.err</string>
</dict>
</plist>
""", encoding="utf-8")
    subprocess.run(["launchctl", "load", "-w", str(plist)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _disable_autostart_macos() -> None:
    plist = Path(os.path.expanduser("~/Library/LaunchAgents/it.givegroup.engine.plist"))
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        plist.unlink(missing_ok=True)


def _enable_autostart_linux() -> None:
    autostart_dir = Path(os.path.expanduser("~/.config/autostart"))
    autostart_dir.mkdir(parents=True, exist_ok=True)
    src = Path(os.path.expanduser("~/.local/share/applications/givengine.desktop"))
    dest = autostart_dir / "givengine.desktop"
    if src.exists():
        shutil.copyfile(src, dest)
    else:
        icon = GIVE_HOME / "resources" / "icon.png"
        dest.write_text(f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Gi.Ve Engine
Comment=Il motore IA che accelera il tuo business
Exec=bash -c 'source "{GIVE_HOME}/.venv/bin/activate" && cd "{GIVE_HOME}" && exec python -m core.orchestrator'
Icon={icon}
Terminal=false
Categories=Development;Utility;Office;
StartupNotify=true
StartupWMClass=givengine
""", encoding="utf-8")
    os.chmod(dest, 0o600)


def _disable_autostart_linux() -> None:
    dest = Path(os.path.expanduser("~/.config/autostart/givengine.desktop"))
    dest.unlink(missing_ok=True)


def _enable_autostart_windows() -> None:
    try:
        import winreg  # type: ignore
    except ImportError as e:
        raise RuntimeError("winreg non disponibile") from e

    vbs = GIVE_HOME / "launcher.vbs"
    if not vbs.exists():
        pyw = _venv_pythonw_win()
        give_str = str(GIVE_HOME).replace("\\", "\\\\")
        pyw_str = pyw.replace("\\", "\\\\")
        vbs.write_text(
            "Set WshShell = CreateObject(\"WScript.Shell\")\n"
            f"WshShell.CurrentDirectory = \"{give_str}\"\n"
            f"WshShell.Run \"\"\"{pyw_str}\"\"\" & \" -m core.orchestrator\", 0, False\n",
            encoding="ascii",
        )

    cmd = f'wscript.exe "{vbs}"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, "Gi.Ve Engine", 0, winreg.REG_SZ, cmd)


def _disable_autostart_windows() -> None:
    try:
        import winreg  # type: ignore
    except ImportError:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "Gi.Ve Engine")
    except OSError:
        pass


def expose_lan_pref() -> bool:
    """Persisted user intent for "Esponi su rete locale" toggle."""
    return bool(get_pref("expose_lan", False))


def set_expose_lan(enabled: bool) -> None:
    set_pref("expose_lan", bool(enabled))


def snapshot() -> dict:
    return {
        "os": os_name(),
        "os_label": os_label(),
        "shortcut_location": shortcut_location_label(),
        "is_first_launch": is_first_launch(),
        "autostart": autostart_is_enabled(),
        "autostart_shell": shell_autostart_is_enabled(),
        "expose_lan": expose_lan_pref(),
        "give_home": str(GIVE_HOME),
    }


# --- BYOK: chiave API Anthropic dell'utente -----------------------------------
# Storage SOLO locale in ~/.givengine/credentials.json (perm 0600). La chiave
# non lascia mai la macchina dell'utente: nessun endpoint Gi.Ve la riceve
# (Punto Cardine 14). `_check_anthropic_key` in ai_environment.py legge lo
# stesso file (campo `anthropic_api_key`) per riportarne la sola presenza.
_BYOK_FIELD = "anthropic_api_key"


def _credentials_file() -> Path:
    return GIVE_HOME / "credentials.json"


def _read_credentials() -> dict:
    f = _credentials_file()
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_credentials(data: dict) -> None:
    f = _credentials_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(f.parent, 0o700)
    except OSError:
        pass
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Scrittura atomica e sicura. mkstemp crea un file NUOVO e univoco con
    # O_CREAT|O_EXCL a modalità 0600 (niente symlink-following, niente clobber);
    # dopo fsync, os.replace() lo sposta sul nome finale con un rename atomico.
    # Garanzie: il nome finale punta sempre a un inode appena creato a 0600 —
    # nessuna finestra con permessi larghi — e os.replace NON scrive attraverso
    # un eventuale symlink piazzato al posto di credentials.json (lo sostituisce).
    fd, tmp_name = tempfile.mkstemp(
        dir=str(f.parent), prefix=".credentials-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, f)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_byok_key() -> str | None:
    """Chiave API Anthropic salvata (valore in chiaro). Solo uso interno."""
    key = _read_credentials().get(_BYOK_FIELD)
    return key.strip() if isinstance(key, str) and key.strip() else None


def _mask_key(key: str) -> str:
    """Maschera la chiave per la UI: prefisso + ultime 4 cifre, mai il valore intero."""
    k = key.strip()
    if len(k) <= 12:
        return "••••"
    return f"{k[:7]}…{k[-4:]}"


def save_byok_key(api_key: str) -> None:
    """Salva la chiave API Anthropic in credentials.json (perm 0600).

    Args:
        api_key: la chiave in chiaro fornita dall'utente.

    Raises:
        ValueError: se la chiave è vuota.
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("chiave vuota")
    data = _read_credentials()
    data[_BYOK_FIELD] = key
    _write_credentials(data)


def clear_byok_key() -> bool:
    """Rimuove la chiave salvata. Ritorna True se c'era qualcosa da rimuovere."""
    data = _read_credentials()
    if _BYOK_FIELD not in data:
        return False
    del data[_BYOK_FIELD]
    _write_credentials(data)
    return True


def byok_status() -> dict:
    """Stato BYOK per la UI. Non espone mai la chiave intera."""
    key = _read_byok_key()
    return {"configured": bool(key), "masked": _mask_key(key) if key else None}
