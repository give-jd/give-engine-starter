"""Unit tests CRUD scadenze + storico pagamenti + template ITA."""
from __future__ import annotations
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE_DIR))
import app  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript((RECIPE_DIR / "schema.sql").read_text())
    c.row_factory = sqlite3.Row
    return c


def test_add_scadenza_inserts(conn):
    app.add_scadenza(conn, "auto", "Bollo", "Targa AB123CD", date.today() + timedelta(days=30), "custom", 360, 250.0, "Test")
    r = app.list_scadenze(conn)
    assert len(r) == 1
    assert r[0]["tipo"] == "Bollo"
    assert r[0]["importo_previsto_eur"] == pytest.approx(250.0)


def test_list_scadenze_filter_prossime(conn):
    app.add_scadenza(conn, "auto", "Vicino", "", date.today() + timedelta(days=30), "custom", 360, None, None)
    app.add_scadenza(conn, "auto", "Lontano", "", date.today() + timedelta(days=120), "custom", 360, None, None)
    near = app.list_scadenze(conn, prossime_giorni=60)
    assert len(near) == 1
    assert near[0]["tipo"] == "Vicino"


def test_list_scadenze_ordered_by_date(conn):
    app.add_scadenza(conn, "auto", "Late", "", date.today() + timedelta(days=60), "custom", 360, None, None)
    app.add_scadenza(conn, "auto", "Early", "", date.today() + timedelta(days=10), "custom", 360, None, None)
    r = app.list_scadenze(conn)
    assert r[0]["tipo"] == "Early"


def test_mark_paid_advances_date(conn):
    initial = date.today() + timedelta(days=10)
    app.add_scadenza(conn, "auto", "Bollo", "", initial, "custom", 360, 100, None)
    sid = app.list_scadenze(conn)[0]["id"]
    app.mark_paid(conn, sid, 100.0, "bonifico")
    after = app.list_scadenze(conn)[0]
    assert date.fromisoformat(after["prossima_scadenza"]) > initial


def test_mark_paid_records_storico(conn):
    app.add_scadenza(conn, "auto", "Bollo", "", date.today() + timedelta(days=10), "custom", 360, 100, None)
    sid = app.list_scadenze(conn)[0]["id"]
    app.mark_paid(conn, sid, 95.50, "carta")
    storico = app.get_storico(conn)
    assert len(storico) == 1
    assert storico[0]["importo_pagato_eur"] == pytest.approx(95.50)
    assert storico[0]["metodo"] == "carta"


def test_delete_scadenza_removes(conn):
    app.add_scadenza(conn, "casa", "Caldaia", "", date.today() + timedelta(days=30), "custom", 360, None, None)
    sid = app.list_scadenze(conn)[0]["id"]
    app.delete_scadenza(conn, sid)
    assert app.list_scadenze(conn) == []


def test_template_italiani_count_12():
    assert len(app.TEMPLATE_ITALIANI) == 12
    cats = {t[0] for t in app.TEMPLATE_ITALIANI}
    assert {"auto", "casa", "persona"} == cats


def test_template_format_4_fields():
    for t in app.TEMPLATE_ITALIANI:
        assert len(t) == 4


def test_mark_paid_mensile_advances_one_calendar_month(conn):
    initial = date(2026, 1, 31)
    app.add_scadenza(conn, "casa", "Affitto", "", initial, "mensile", None, 500, None)
    sid = app.list_scadenze(conn)[0]["id"]
    app.mark_paid(conn, sid, 500.0, "bonifico")
    after = date.fromisoformat(app.list_scadenze(conn)[0]["prossima_scadenza"])
    # +1 mese di calendario (31 gen -> 28 feb 2026, non +30 giorni)
    assert (after.year, after.month) == (2026, 2)


def test_mark_paid_una_tantum_no_advance(conn):
    d = date.today() + timedelta(days=10)
    app.add_scadenza(conn, "auto", "Multa", "", d, "una-tantum", None, 80, None)
    sid = app.list_scadenze(conn)[0]["id"]
    app.mark_paid(conn, sid, 80.0, "carta")
    after = date.fromisoformat(app.list_scadenze(conn)[0]["prossima_scadenza"])
    assert after == d  # non si ripete: data invariata


def test_update_scadenza(conn):
    app.add_scadenza(conn, "auto", "Bollo", "", date.today(), "custom", 360, 100, None)
    sid = app.list_scadenze(conn)[0]["id"]
    app.update_scadenza(conn, sid, "auto", "Bollo Auto", "AB123CD", date(2026, 8, 5),
                        "mensile", None, 120, "agg")
    r = app.list_scadenze(conn)[0]
    assert r["tipo"] == "Bollo Auto"
    assert r["prossima_scadenza"] == "2026-08-05"
    assert r["frequenza_tipo"] == "mensile"
