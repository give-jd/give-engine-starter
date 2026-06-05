"""Test per core/shared/notifier.py (notifiche OS best-effort)."""

from __future__ import annotations

import sys
import types

import pytest

from core.shared import notifier


class TestPlyer:
    def test_plyer_present(self, monkeypatch):
        fake = types.ModuleType("plyer")
        fake.notification = types.SimpleNamespace(notify=lambda **k: None)
        monkeypatch.setitem(sys.modules, "plyer", fake)
        assert notifier._notify_via_plyer("t", "m") is True

    def test_plyer_absent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "plyer", None)
        assert notifier._notify_via_plyer("t", "m") is False


class TestNative:
    def test_macos_no_binary(self, monkeypatch):
        monkeypatch.setattr(notifier.shutil, "which", lambda b: None)
        assert notifier._notify_macos("t", "m") is False

    def test_macos_ok(self, monkeypatch):
        monkeypatch.setattr(notifier.shutil, "which", lambda b: "/usr/bin/osascript")
        monkeypatch.setattr(notifier.subprocess, "run", lambda *a, **k: None)
        assert notifier._notify_macos('a"b', 'c"d') is True

    def test_macos_subprocess_error(self, monkeypatch):
        monkeypatch.setattr(notifier.shutil, "which", lambda b: "/x")

        def boom(*a, **k):
            raise notifier.subprocess.SubprocessError("x")

        monkeypatch.setattr(notifier.subprocess, "run", boom)
        assert notifier._notify_macos("t", "m") is False

    def test_linux_no_binary(self, monkeypatch):
        monkeypatch.setattr(notifier.shutil, "which", lambda b: None)
        assert notifier._notify_linux("t", "m") is False

    def test_linux_ok(self, monkeypatch):
        monkeypatch.setattr(notifier.shutil, "which", lambda b: "/usr/bin/notify-send")
        monkeypatch.setattr(notifier.subprocess, "run", lambda *a, **k: None)
        assert notifier._notify_linux("t", "m") is True

    def test_windows_ok(self, monkeypatch):
        monkeypatch.setattr(notifier.subprocess, "run", lambda *a, **k: None)
        assert notifier._notify_windows("t", "m") is True

    def test_windows_error(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("x")

        monkeypatch.setattr(notifier.subprocess, "run", boom)
        assert notifier._notify_windows("t", "m") is False


class TestNotifyOs:
    def test_via_plyer(self, monkeypatch):
        monkeypatch.setattr(notifier, "_notify_via_plyer", lambda t, m: True)
        assert notifier.notify_os("t", "m") is True

    @pytest.mark.parametrize("sysname,fn", [
        ("darwin", "_notify_macos"), ("linux", "_notify_linux"), ("windows", "_notify_windows"),
    ])
    def test_dispatch_by_platform(self, monkeypatch, sysname, fn):
        monkeypatch.setattr(notifier, "_notify_via_plyer", lambda t, m: False)
        monkeypatch.setattr(notifier.platform, "system", lambda: sysname)
        monkeypatch.setattr(notifier, fn, lambda t, m: True)
        assert notifier.notify_os("t", "m") is True

    def test_unknown_platform(self, monkeypatch):
        monkeypatch.setattr(notifier, "_notify_via_plyer", lambda t, m: False)
        monkeypatch.setattr(notifier.platform, "system", lambda: "plan9")
        assert notifier.notify_os("t", "m") is False


class TestIsAvailable:
    def test_plyer_available(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "plyer", types.ModuleType("plyer"))
        assert notifier.is_available() is True

    def test_linux_notify_send(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "plyer", None)
        monkeypatch.setattr(notifier.platform, "system", lambda: "linux")
        monkeypatch.setattr(notifier.shutil, "which", lambda b: "/usr/bin/notify-send")
        assert notifier.is_available() is True

    def test_unknown_platform_false(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "plyer", None)
        monkeypatch.setattr(notifier.platform, "system", lambda: "plan9")
        assert notifier.is_available() is False
