"""UI test (streamlit AppTest) osservaprezzi-carburanti — render con dati."""

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
    services.upsert_distributore(conn, {
        "id": 1, "bandiera": "Q8", "comune": "Milano", "provincia": "MI",
        "nome_impianto": "Q8 Test", "latitudine": 45.46, "longitudine": 9.19,
    })
    services.add_rifornimento(conn, {
        "distributore_id": 1, "data": "2026-01-15", "carburante": "Benzina",
        "litri": 40.0, "prezzo_unitario": 1.85, "km_attuali": 50000,
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
