"""Smoke test: app.py starts without exceptions (streamlit AppTest)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

_APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("CURRICULUM_DB", str(tmp_path / "smoke.db"))
    at = AppTest.from_file(_APP, default_timeout=60).run()
    assert not at.exception
