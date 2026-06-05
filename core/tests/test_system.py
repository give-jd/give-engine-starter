"""Test per core/system.py (OS helpers: prefs, first-launch, autostart)."""

from __future__ import annotations

import json

import pytest

from core import system as sysmod


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirige GIVE_HOME, prefs/marker e HOME su tmp."""
    home = tmp_path / "home"
    home.mkdir()
    give = tmp_path / "givengine"
    monkeypatch.setattr(sysmod, "GIVE_HOME", give)
    monkeypatch.setattr(sysmod, "PREFS_FILE", give / "preferences.json")
    monkeypatch.setattr(sysmod, "FIRST_LAUNCH_MARKER", give / ".first_launch_done")
    monkeypatch.setenv("HOME", str(home))
    yield


class TestOsName:
    @pytest.mark.parametrize(
        "sysret,expected",
        [("Darwin", "macos"), ("Linux", "linux"), ("Windows", "windows"), ("Plan9", "plan9")],
    )
    def test_os_name(self, monkeypatch, sysret, expected):
        monkeypatch.setattr(sysmod.platform, "system", lambda: sysret)
        assert sysmod.os_name() == expected

    def test_os_label(self, monkeypatch):
        monkeypatch.setattr(sysmod, "os_name", lambda: "macos")
        assert sysmod.os_label() == "Mac"

    def test_shortcut_location_label(self, monkeypatch):
        monkeypatch.setattr(sysmod, "os_name", lambda: "windows")
        assert "Desktop" in sysmod.shortcut_location_label()


class TestPrefs:
    def test_load_missing_empty(self):
        assert sysmod._load_prefs() == {}

    def test_load_corrupt(self):
        sysmod.PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        sysmod.PREFS_FILE.write_text("{nope", encoding="utf-8")
        assert sysmod._load_prefs() == {}

    def test_get_set_roundtrip(self):
        assert sysmod.get_pref("x", "def") == "def"
        sysmod.set_pref("x", 42)
        assert sysmod.get_pref("x") == 42
        on_disk = json.loads(sysmod.PREFS_FILE.read_text(encoding="utf-8"))
        assert on_disk["x"] == 42

    def test_expose_lan_pref(self):
        assert sysmod.expose_lan_pref() is False
        sysmod.set_expose_lan(True)
        assert sysmod.expose_lan_pref() is True


class TestFirstLaunch:
    def test_first_launch_true_then_done(self):
        assert sysmod.is_first_launch() is True
        sysmod.mark_first_launch_done()
        assert sysmod.is_first_launch() is False


class TestVenvPython:
    def test_venv_python_fallback_executable(self, monkeypatch):
        monkeypatch.setattr(sysmod.sys, "platform", "linux")
        assert sysmod._venv_python() == sysmod.sys.executable

    def test_venv_python_existing(self, monkeypatch):
        monkeypatch.setattr(sysmod.sys, "platform", "linux")
        venv_py = sysmod.GIVE_HOME / ".venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True, exist_ok=True)
        venv_py.write_text("#!/bin/sh\n")
        assert sysmod._venv_python() == str(venv_py)


class TestAutostartLinux:
    def test_enabled_false_when_absent(self, monkeypatch):
        monkeypatch.setattr(sysmod, "os_name", lambda: "linux")
        assert sysmod.autostart_is_enabled() is False

    def test_enable_then_detected_then_disable(self, monkeypatch):
        monkeypatch.setattr(sysmod, "os_name", lambda: "linux")
        ok, msg = sysmod.enable_autostart()
        assert ok is True and "attivato" in msg
        assert sysmod.autostart_is_enabled() is True
        assert sysmod.get_pref("autostart") is True
        ok2, _ = sysmod.disable_autostart()
        assert ok2 is True
        assert sysmod.autostart_is_enabled() is False
        assert sysmod.get_pref("autostart") is False

    def test_enable_unsupported_os(self, monkeypatch):
        monkeypatch.setattr(sysmod, "os_name", lambda: "plan9")
        ok, msg = sysmod.enable_autostart()
        assert ok is False and "non supportato" in msg


class TestSnapshot:
    def test_snapshot_shape(self, monkeypatch):
        monkeypatch.setattr(sysmod, "os_name", lambda: "linux")
        snap = sysmod.snapshot()
        assert snap["os"] == "linux"
        assert set(snap) >= {"os", "os_label", "shortcut_location", "is_first_launch",
                             "autostart", "expose_lan", "give_home"}


class TestByok:
    def test_status_empty_by_default(self):
        st = sysmod.byok_status()
        assert st == {"configured": False, "masked": None}
        assert sysmod._read_byok_key() is None

    def test_save_read_roundtrip(self):
        sysmod.save_byok_key("sk-ant-api03-ABCDEFGHIJKLMNOP")
        assert sysmod._read_byok_key() == "sk-ant-api03-ABCDEFGHIJKLMNOP"
        st = sysmod.byok_status()
        assert st["configured"] is True
        # mai la chiave intera nella UI: prefisso + ultime 4
        assert st["masked"].startswith("sk-ant-")
        assert st["masked"].endswith("MNOP")
        assert "ABCDEFGHIJKL" not in st["masked"]

    def test_save_rejects_empty(self):
        with pytest.raises(ValueError):
            sysmod.save_byok_key("   ")

    def test_file_is_0600(self):
        sysmod.save_byok_key("sk-ant-secret-value-123456")
        mode = sysmod._credentials_file().stat().st_mode & 0o777
        assert mode == 0o600

    def test_tightens_preexisting_loose_file(self):
        import os

        f = sysmod._credentials_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}", encoding="utf-8")
        os.chmod(f, 0o644)
        sysmod.save_byok_key("sk-ant-secret-value-123456")
        assert (f.stat().st_mode & 0o777) == 0o600

    def test_clear_idempotent(self):
        sysmod.save_byok_key("sk-ant-secret-value-123456")
        assert sysmod.clear_byok_key() is True
        assert sysmod.byok_status()["configured"] is False
        assert sysmod.clear_byok_key() is False

    def test_preserves_other_credential_fields(self):
        sysmod._write_credentials({"other": "keep-me"})
        sysmod.save_byok_key("sk-ant-secret-value-123456")
        sysmod.clear_byok_key()
        assert sysmod._read_credentials() == {"other": "keep-me"}

    def test_does_not_write_through_symlink(self, tmp_path):
        import os

        # credentials.json è un symlink verso un file "esterno" (es. piazzato
        # da un attaccante). La scrittura NON deve seguire il link.
        outside = tmp_path / "outside_target"
        outside.write_text("ORIGINAL", encoding="utf-8")
        f = sysmod._credentials_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(outside, f)

        sysmod.save_byok_key("sk-ant-secret-value-123456")

        # il target esterno resta intatto; il path finale è ora un file regolare 0600
        assert outside.read_text(encoding="utf-8") == "ORIGINAL"
        assert not f.is_symlink()
        assert (f.stat().st_mode & 0o777) == 0o600
        assert sysmod._read_byok_key() == "sk-ant-secret-value-123456"
