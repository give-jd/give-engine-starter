"""Unit tests utenze + letture + dashboard consumo delta."""
from __future__ import annotations
import sqlite3
import sys
from datetime import date
from pathlib import Path
import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE_DIR))
import app


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript((RECIPE_DIR / "schema.sql").read_text())
    c.row_factory = sqlite3.Row
    return c


def test_add_utenza_inserts(conn):
    app.add_utenza(conn, "gas", "PDR12345", "Eni", "Casa Milano", False)
    r = app.list_utenze(conn)
    assert len(r) == 1
    assert r[0]["tipo"] == "gas"
    assert r[0]["unita_misura"] == "smc"


def test_unita_misura_auto_per_tipo(conn):
    app.add_utenza(conn, "luce", None, None, "Casa", False)
    app.add_utenza(conn, "acqua", None, None, "Casa", False)
    app.add_utenza(conn, "gas", None, None, "Casa", False)
    types = {u["tipo"]: u["unita_misura"] for u in app.list_utenze(conn)}
    assert types == {"luce": "kWh", "acqua": "mc", "gas": "smc"}


def test_add_lettura_inserts(conn):
    app.add_utenza(conn, "gas", "PDR", "Eni", "Casa", False)
    uid = app.list_utenze(conn)[0]["id"]
    app.add_lettura(conn, uid, date.today(), 1500.5, None, None, None, "test")
    r = app.list_letture(conn, uid)
    assert len(r) == 1
    assert r[0]["valore"] == pytest.approx(1500.5)


def test_calcola_consumi_delta(conn):
    app.add_utenza(conn, "gas", None, None, "Casa", False)
    uid = app.list_utenze(conn)[0]["id"]
    app.add_lettura(conn, uid, date(2026, 1, 1), 1000.0, None, None, None, None)
    app.add_lettura(conn, uid, date(2026, 2, 1), 1100.0, None, None, None, None)
    app.add_lettura(conn, uid, date(2026, 3, 1), 1230.0, None, None, None, None)
    letture = app.list_letture(conn, uid)
    df = app.calcola_consumi(letture)
    consumi = df["consumo"].dropna().tolist()
    assert consumi == [100.0, 130.0]


def test_calcola_consumi_empty():
    df = app.calcola_consumi([])
    assert df.empty


def test_letture_ordered_desc(conn):
    app.add_utenza(conn, "gas", None, None, "Casa", False)
    uid = app.list_utenze(conn)[0]["id"]
    app.add_lettura(conn, uid, date(2026, 1, 1), 100, None, None, None, None)
    app.add_lettura(conn, uid, date(2026, 3, 1), 300, None, None, None, None)
    r = app.list_letture(conn, uid)
    assert r[0]["data_lettura"] >= r[1]["data_lettura"]
