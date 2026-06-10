"""Test regolamento 'dove butto X' + preset riferimenti."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from modules import riferimenti, services  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    services.init_db(c)
    yield c
    c.close()


def test_preset_frazioni_complete():
    nomi = {f["nome"] for f in riferimenti.FRAZIONI_PRESET}
    for atteso in ["Umido", "Indifferenziato", "Carta e cartone",
                   "Plastica e lattine", "Vetro", "Verde e sfalci",
                   "RAEE", "Ingombranti", "Farmaci", "Pile e batterie"]:
        assert atteso in nomi
    for f in riferimenti.FRAZIONI_PRESET:
        assert f["colore"] and f["icona"]


def test_disclaimer_presente():
    assert "verifica" in riferimenti.DISCLAIMER.lower()
    assert riferimenti.REGOLAMENTO_DEFAULT  # non vuoto


def test_frazione_preset_lookup():
    assert riferimenti.frazione_preset("umido") is not None
    assert riferimenti.frazione_preset("inesistente") is None


def test_cerca_materiale_match(conn):
    fid = services.add_frazione(conn, {"nome": "Umido"})
    services.add_voce_regolamento(conn, {
        "materiale": "fondi di caffe", "frazione_id": fid, "note": "scarto cucina",
    })
    out = services.cerca_materiale(conn, "caffe")
    assert len(out) == 1
    assert out[0]["frazione"] == "Umido"


def test_cerca_materiale_match_su_note(conn):
    fid = services.add_frazione(conn, {"nome": "Indifferenziato"})
    services.add_voce_regolamento(conn, {
        "materiale": "spazzolino", "frazione_id": fid, "note": "plastica non riciclabile",
    })
    out = services.cerca_materiale(conn, "riciclabile")
    assert out and out[0]["materiale"] == "spazzolino"


def test_cerca_materiale_miss(conn):
    fid = services.add_frazione(conn, {"nome": "Vetro"})
    services.add_voce_regolamento(conn, {"materiale": "bottiglia", "frazione_id": fid})
    assert services.cerca_materiale(conn, "uranio") == []


def test_cerca_materiale_query_vuota(conn):
    assert services.cerca_materiale(conn, "") == []
    assert services.cerca_materiale(conn, "   ") == []
