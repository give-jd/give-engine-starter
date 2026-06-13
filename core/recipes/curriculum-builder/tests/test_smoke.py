from streamlit.testing.v1 import AppTest


def test_app_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("CURRICULUM_DB", str(tmp_path / "smoke.db"))
    at = AppTest.from_file("app.py", default_timeout=60).run()
    assert not at.exception
