"""Smoke test: import app + moduli senza errori e senza st.* a import-time."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))


def test_import_app_senza_streamlit():
    # streamlit NON e' importato a import-time: l'import di app non deve fallire.
    import app  # noqa: F401
    assert hasattr(app, "main")
    assert callable(app.main)
    assert hasattr(app, "get_conn")
    for fn in ("render_oggi", "render_calendario", "render_importa",
               "render_regolamento", "render_impostazioni"):
        assert hasattr(app, fn)


def test_import_moduli():
    services = importlib.import_module("modules.services")
    riferimenti = importlib.import_module("modules.riferimenti")
    assert hasattr(services, "prossime_raccolte")
    assert riferimenti.FRAZIONI_PRESET


def test_import_parsers():
    parsers = importlib.import_module("parsers")
    assert hasattr(parsers, "detect_parser")
    assert hasattr(parsers, "estrai_testo")
