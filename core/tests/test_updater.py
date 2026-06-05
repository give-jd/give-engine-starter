"""Test per core/updater.py — l'auto-update non deve mai partire 'per sbaglio'
(offline, già aggiornato, disattivato) né fare rete nei test."""

from __future__ import annotations

from core import updater


def _boom(*a, **k):
    raise AssertionError("non deve essere chiamato")


def test_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("GIVE_NO_UPDATE", "1")
    monkeypatch.setattr(updater, "_remote_sha", _boom)  # nessuna rete
    updater.maybe_self_update(False, [])  # non solleva


def test_noop_when_already_updated(monkeypatch):
    monkeypatch.delenv("GIVE_NO_UPDATE", raising=False)
    monkeypatch.setattr(updater, "_remote_sha", _boom)
    updater.maybe_self_update(True, [])  # already_updated → no-op


def test_noop_when_sha_unchanged(monkeypatch):
    monkeypatch.delenv("GIVE_NO_UPDATE", raising=False)
    from core import system as sysmod
    monkeypatch.setattr(sysmod, "get_pref",
                        lambda k, d=None: "abc123" if k == "last_update_sha" else d)
    monkeypatch.setattr(updater, "_remote_sha", lambda *a, **k: "abc123")
    called = {"dl": False}
    monkeypatch.setattr(updater, "_download_and_extract",
                        lambda d: called.__setitem__("dl", True))
    updater.maybe_self_update(False, [])
    assert called["dl"] is False  # stessa versione → niente download/re-exec


def test_offline_no_crash(monkeypatch):
    monkeypatch.delenv("GIVE_NO_UPDATE", raising=False)
    from core import system as sysmod
    monkeypatch.setattr(sysmod, "get_pref", lambda k, d=None: None)
    monkeypatch.setattr(updater, "_remote_sha", lambda *a, **k: None)  # offline
    updater.maybe_self_update(False, [])  # non solleva, non ri-esegue
