"""UI smoke (streamlit AppTest) per app.py — render senza crash su DB vuoto.

HOME->tmp redirige Path.home() (DB su tmp). Esercita main()/render top-level
che gli smoke test non toccano.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

_APP = str(RECIPE_DIR / "app.py")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_app_runs_no_exception(home):
    at = AppTest.from_file(_APP, default_timeout=60).run()
    assert not at.exception
