"""Unit tests geo Haversine + search distributori + CRUD rifornimenti."""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

import app  # noqa


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript((RECIPE_DIR / "schema.sql").read_text(encoding="utf-8"))
    c.row_factory = sqlite3.Row
    c.execute("INSERT INTO distributori (id,bandiera,nome_impianto,comune,provincia,latitudine,longitudine) VALUES (1,'Eni','Milano Duomo','Milano','MI',45.4642,9.1900)")
    c.execute("INSERT INTO distributori (id,bandiera,nome_impianto,comune,provincia,latitudine,longitudine) VALUES (2,'Q8','Bergamo Citta','Bergamo','BG',45.6983,9.6773)")
    c.execute("INSERT INTO distributori (id,bandiera,nome_impianto,comune,provincia,latitudine,longitudine) VALUES (3,'IP','Como Lago','Como','CO',45.8081,9.0852)")
    c.execute("INSERT INTO distributori (id,bandiera,nome_impianto,comune,provincia,latitudine,longitudine) VALUES (4,'Esso','Torino Mole','Torino','TO',45.0703,7.6869)")
    c.execute("INSERT INTO prezzi (distributore_id,carburante,prezzo_self,data_comunicazione) VALUES (1,'Benzina',1.795,'2026-05-25T08:00')")
    c.execute("INSERT INTO prezzi (distributore_id,carburante,prezzo_self,data_comunicazione) VALUES (2,'Benzina',1.745,'2026-05-25T08:00')")
    c.execute("INSERT INTO prezzi (distributore_id,carburante,prezzo_self,data_comunicazione) VALUES (3,'Benzina',1.812,'2026-05-25T08:00')")
    c.execute("INSERT INTO prezzi (distributore_id,carburante,prezzo_self,data_comunicazione) VALUES (4,'Benzina',1.789,'2026-05-25T08:00')")
    c.commit()
    return c


def test_nearest_milano_5km_only_milano(conn):
    r = app.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", 5.0)
    ids = [x["id"] for x in r]
    assert ids == [1]


def test_nearest_milano_60km_includes_bergamo_como(conn):
    r = app.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", 60.0)
    ids = [x["id"] for x in r]
    assert 1 in ids and 2 in ids and 3 in ids
    assert 4 not in ids


def test_nearest_sorted_by_distance(conn):
    r = app.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", 200.0)
    distances = [x["distanza_km"] for x in r]
    assert distances == sorted(distances)


def test_nearest_returns_distance_field(conn):
    r = app.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", 60.0)
    for x in r:
        assert "distanza_km" in x
        assert isinstance(x["distanza_km"], (int, float))
        assert x["distanza_km"] >= 0


def test_nearest_respects_limit(conn):
    r = app.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", 1000.0, limit=2)
    assert len(r) <= 2


def test_nearest_filters_null_coords(conn):
    conn.execute("INSERT INTO distributori (id,nome_impianto,latitudine,longitudine) VALUES (99,'No coords',NULL,NULL)")
    conn.commit()
    r = app.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", 1000.0)
    ids = [x["id"] for x in r]
    assert 99 not in ids


def test_nearest_empty_result_no_match(conn):
    r = app.nearest_by_coords(conn, 0.0, 0.0, "Benzina", 10.0)
    assert r == []


def test_search_distributori_milano(conn):
    r = app.search_distributori(conn, "Milano", "Benzina")
    assert len(r) >= 1
    assert all("milano" in x["comune"].lower() for x in r)


def test_search_distributori_case_insensitive(conn):
    r1 = app.search_distributori(conn, "milano", "Benzina")
    r2 = app.search_distributori(conn, "MILANO", "Benzina")
    assert len(r1) == len(r2) > 0


def test_search_distributori_partial_match(conn):
    r = app.search_distributori(conn, "ila", "Benzina")
    assert any("milano" in x["comune"].lower() for x in r)


def test_search_distributori_empty_no_match(conn):
    r = app.search_distributori(conn, "ComuneInesistente", "Benzina")
    assert r == []


def test_add_rifornimento_and_list(conn):
    app.add_rifornimento(conn, 1, date(2026, 5, 20), "Benzina", 35.5, 1.795, 12500, "Pieno")
    r = app.list_rifornimenti(conn)
    assert len(r) == 1
    assert r[0]["litri"] == pytest.approx(35.5)
    assert r[0]["prezzo_totale"] == pytest.approx(35.5 * 1.795, rel=1e-3)


def test_add_rifornimento_orders_desc(conn):
    app.add_rifornimento(conn, 1, date(2026, 5, 1), "Benzina", 30, 1.79, 12000, None)
    app.add_rifornimento(conn, 1, date(2026, 5, 20), "Benzina", 35, 1.80, 12500, None)
    r = app.list_rifornimenti(conn)
    assert r[0]["data"] >= r[1]["data"]
