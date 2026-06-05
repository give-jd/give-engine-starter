"""UI test (streamlit AppTest) scadenze-auto-casa — render tab con dati."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

import app  # noqa: E402
from modules import services  # noqa: E402

_APP = str(RECIPE_DIR / "app.py")


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    importlib.reload(app)
    conn = app.get_conn()
    services.add_scadenza(conn, {
        "categoria": "auto", "tipo": "bollo", "prossima_scadenza": "2027-01-01",
        "frequenza_tipo": "annuale", "importo_previsto_eur": 120.0,
    })
    conn.close()
    return tmp_path


def test_runs_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    at = AppTest.from_file(_APP, default_timeout=60).run()
    assert not at.exception


def test_renders_with_data(seeded):
    at = AppTest.from_file(_APP, default_timeout=60).run()
    assert not at.exception
    assert at.tabs
