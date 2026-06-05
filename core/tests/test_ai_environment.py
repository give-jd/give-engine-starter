"""Test per core/ai_environment.py (detection tooling IA esterno)."""

from __future__ import annotations

import json
import subprocess

import pytest

from core import ai_environment as ai


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    give = tmp_path / "givengine"
    monkeypatch.setattr(ai, "GIVE_HOME", give)
    monkeypatch.setattr(ai, "CACHE_FILE", give / "ai_environment.json")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


class TestHelpers:
    @pytest.mark.parametrize(
        "sysret,expected",
        [("Darwin", "macos"), ("Linux", "linux"), ("Windows", "windows"), ("Foo", "foo")],
    )
    def test_os_name(self, monkeypatch, sysret, expected):
        monkeypatch.setattr(ai.platform, "system", lambda: sysret)
        assert ai._os_name() == expected

    def test_now_iso(self):
        assert ai._now_iso().endswith("Z")

    def test_safe_exists(self, tmp_path):
        f = tmp_path / "x"
        f.write_text("y")
        assert ai._safe_exists(None, "", str(f)) == str(f)
        assert ai._safe_exists("/no/such/path/zzz") is None

    def test_safe_which(self, monkeypatch):
        monkeypatch.setattr(ai.shutil, "which", lambda b: "/usr/bin/" + b)
        assert ai._safe_which("cursor") == "/usr/bin/cursor"

    def test_safe_which_exception(self, monkeypatch):
        def boom(_):
            raise RuntimeError("x")

        monkeypatch.setattr(ai.shutil, "which", boom)
        assert ai._safe_which("cursor") is None

    def test_safe_version_ok(self, monkeypatch):
        class _R:
            stdout = "v1.2.3\nextra"
            stderr = ""

        monkeypatch.setattr(ai.subprocess, "run", lambda *a, **k: _R())
        assert ai._safe_version(["cursor", "--version"]) == "v1.2.3"

    def test_safe_version_timeout(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="x", timeout=1)

        monkeypatch.setattr(ai.subprocess, "run", boom)
        assert ai._safe_version(["x"]) is None

    def test_registry_has_non_windows(self, monkeypatch):
        monkeypatch.setattr(ai, "_os_name", lambda: "linux")
        assert ai._registry_has("Software\\X") is False


class TestChecks:
    def test_check_cursor_linux_installed(self, monkeypatch):
        monkeypatch.setattr(ai, "_os_name", lambda: "linux")
        monkeypatch.setattr(ai, "_safe_which", lambda b: "/usr/bin/cursor" if b == "cursor" else None)
        monkeypatch.setattr(ai.shutil, "which", lambda b: None)  # niente version
        res = ai._check_cursor()
        assert res["installed"] is True and res["path"] == "/usr/bin/cursor"

    def test_check_cursor_not_installed(self, monkeypatch):
        monkeypatch.setattr(ai, "_os_name", lambda: "linux")
        monkeypatch.setattr(ai, "_safe_which", lambda b: None)
        monkeypatch.setattr(ai, "_safe_exists", lambda *a: None)
        assert ai._check_cursor()["installed"] is False

    def test_check_windsurf_linux(self, monkeypatch):
        monkeypatch.setattr(ai, "_os_name", lambda: "linux")
        monkeypatch.setattr(ai, "_safe_which", lambda b: "/usr/bin/windsurf" if b == "windsurf" else None)
        monkeypatch.setattr(ai.shutil, "which", lambda b: None)
        assert ai._check_windsurf()["installed"] is True

    def test_check_claude_code(self, monkeypatch):
        monkeypatch.setattr(ai, "_safe_which", lambda b: "/usr/bin/claude")
        monkeypatch.setattr(ai, "_safe_version", lambda *a, **k: "claude 1.0")
        res = ai._check_claude_code()
        assert res["installed"] is True and res["version"] == "claude 1.0"

    def test_check_vscode_linux(self, monkeypatch):
        monkeypatch.setattr(ai, "_os_name", lambda: "linux")
        monkeypatch.setattr(ai, "_safe_which", lambda b: "/usr/bin/code" if b == "code" else None)
        assert ai._check_vscode()["installed"] is True


class TestAnthropicKey:
    def test_givengine_creds(self):
        ai.GIVE_HOME.mkdir(parents=True, exist_ok=True)
        (ai.GIVE_HOME / "credentials.json").write_text(
            json.dumps({"anthropic_api_key": "sk-test"}), encoding="utf-8"
        )
        assert ai._check_anthropic_key() == {"configured": True, "source": "givengine"}

    def test_sdk_creds_file(self, tmp_path):
        sdk = tmp_path / "home" / ".anthropic"
        sdk.mkdir(parents=True, exist_ok=True)
        (sdk / "credentials").write_text("token-data")
        assert ai._check_anthropic_key()["source"] == "anthropic_sdk"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        assert ai._check_anthropic_key() == {"configured": True, "source": "env"}

    def test_none(self):
        assert ai._check_anthropic_key() == {"configured": False, "source": None}


class TestSummarize:
    def test_ready(self):
        s = ai._summarize({"installed": True}, {"installed": False}, {"installed": False}, {"installed": False})
        assert s["recommendation_level"] == "ready" and s["has_any_ide_ai"] is True

    def test_partial(self):
        s = ai._summarize({"installed": False}, {"installed": False}, {"installed": False}, {"installed": True})
        assert s["recommendation_level"] == "partial"

    def test_missing(self):
        s = ai._summarize({"installed": False}, {"installed": False}, {"installed": False}, {"installed": False})
        assert s["recommendation_level"] == "missing"


class TestDetector:
    def test_load_cached_missing(self, tmp_path):
        assert ai.AIEnvironmentDetector(cache_file=tmp_path / "none.json").load_cached() is None

    def test_load_cached_corrupt(self, tmp_path):
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json")
        (tmp_path / "c.json").write_text("{bad", encoding="utf-8")
        assert d.load_cached() is None

    def test_cache_is_fresh_variants(self, tmp_path):
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json")
        assert d.cache_is_fresh() is False  # no file
        d._save({"last_check_at": ai._now_iso()})
        assert d.cache_is_fresh() is True
        d._save({"last_check_at": None})
        assert d.cache_is_fresh() is False
        d._save({"last_check_at": "non-data"})
        assert d.cache_is_fresh() is False
        d._save({"last_check_at": "2000-01-01T00:00:00Z"})
        assert d.cache_is_fresh() is False  # troppo vecchio

    def test_check_builds_and_saves(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ai, "_check_cursor", lambda: {"installed": True, "path": "/c", "version": None})
        monkeypatch.setattr(ai, "_check_windsurf", lambda: {"installed": False, "path": None, "version": None})
        monkeypatch.setattr(ai, "_check_claude_code", lambda: {"installed": False, "path": None, "version": None})
        monkeypatch.setattr(ai, "_check_vscode", lambda: {"installed": False, "path": None, "version": None})
        monkeypatch.setattr(ai, "_check_anthropic_key", lambda: {"configured": True, "source": "env"})
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json")
        payload = d.check()
        assert payload["cursor"]["installed"] is True
        assert payload["summary"]["recommendation_level"] == "ready"
        assert d.load_cached()["summary"]["has_any_ide_ai"] is True

    def test_check_budget_exhausted_uses_defaults(self, tmp_path):
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json", budget_s=0.0)
        payload = d.check()
        assert payload["cursor"] == {"installed": False, "path": None, "version": None}
        assert payload["anthropic_api_key"] == {"configured": False, "source": None}

    def test_status_uses_cache(self, tmp_path):
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json")
        d._save({"platform": "linux", "marker": 1})
        assert d.status()["marker"] == 1

    def test_status_runs_check_when_no_cache(self, tmp_path):
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json", budget_s=0.0)
        assert "summary" in d.status()

    def test_refresh(self, tmp_path):
        d = ai.AIEnvironmentDetector(cache_file=tmp_path / "c.json", budget_s=0.0)
        assert "platform" in d.refresh()

    def test_singleton(self):
        ai._singleton = None
        assert ai.detector() is ai.detector()
