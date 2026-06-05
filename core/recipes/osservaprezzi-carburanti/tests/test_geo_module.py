"""Tests modules/geo.py (Haversine + nearest)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from modules import geo, services  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    services.init_db(c)
    services.upsert_distributore(c, {"id": 1, "bandiera": "Eni",
                                      "comune": "Milano", "provincia": "MI",
                                      "latitudine": 45.4642, "longitudine": 9.1900})
    services.upsert_distributore(c, {"id": 2, "bandiera": "Q8",
                                      "comune": "Bergamo", "provincia": "BG",
                                      "latitudine": 45.6983, "longitudine": 9.6773})
    services.upsert_distributore(c, {"id": 3, "bandiera": "IP",
                                      "comune": "Como", "provincia": "CO",
                                      "latitudine": 45.8081, "longitudine": 9.0852})
    services.aggiorna_prezzo(c, 1, {"carburante": "Benzina", "prezzo_self": 1.795,
                                     "data_comunicazione": "2026-05-25T08:00:00"})
    services.aggiorna_prezzo(c, 2, {"carburante": "Benzina", "prezzo_self": 1.745,
                                     "data_comunicazione": "2026-05-25T08:00:00"})
    services.aggiorna_prezzo(c, 3, {"carburante": "Benzina", "prezzo_self": 1.812,
                                     "data_comunicazione": "2026-05-25T08:00:00"})
    yield c
    c.close()


class TestHaversine:
    def test_milano_bergamo_km(self):
        d = geo.haversine_km(45.4642, 9.1900, 45.6983, 9.6773)
        assert 40 <= d <= 50

    def test_stesso_punto_zero(self):
        d = geo.haversine_km(45.0, 9.0, 45.0, 9.0)
        assert d == pytest.approx(0.0)

    def test_simmetrico(self):
        d1 = geo.haversine_km(45.0, 9.0, 46.0, 10.0)
        d2 = geo.haversine_km(46.0, 10.0, 45.0, 9.0)
        assert abs(d1 - d2) < 0.001


class TestNearestByCoords:
    def test_milano_raggio_breve(self, conn):
        r = geo.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", radius_km=10.0)
        assert len(r) == 1
        assert r[0]["bandiera"] == "Eni"

    def test_milano_raggio_largo(self, conn):
        r = geo.nearest_by_coords(conn, 45.4642, 9.1900, "Benzina", radius_km=100.0)
        assert len(r) >= 2

    def test_ordina_per_prezzo(self, conn):
        r = geo.nearest_by_coords(conn, 45.6, 9.4, "Benzina", radius_km=100.0)
        prezzi = [d["prezzo_self"] for d in r if d.get("prezzo_self") is not None]
        assert prezzi == sorted(prezzi)

    def test_limit(self, conn):
        r = geo.nearest_by_coords(conn, 45.6, 9.4, "Benzina", radius_km=200.0, limit=1)
        assert len(r) <= 1

    def test_zero_risultati(self, conn):
        r = geo.nearest_by_coords(conn, 41.9028, 12.4964, "Benzina", radius_km=1.0)
        assert r == []

    def test_carburante_filtro(self, conn):
        r = geo.nearest_by_coords(conn, 45.4642, 9.1900, "Diesel", radius_km=200.0)
        for d in r:
            assert d.get("prezzo_self") is None


class TestBoundingBox:
    def test_simmetrica(self):
        lat_min, lat_max, lon_min, lon_max = geo.bounding_box(45.0, 9.0, 10.0)
        assert lat_min < 45.0 < lat_max
        assert lon_min < 9.0 < lon_max
        assert abs((lat_max - 45.0) - (45.0 - lat_min)) < 0.001

    def test_raggio_zero(self):
        lat_min, lat_max, _, _ = geo.bounding_box(45.0, 9.0, 0.0)
        assert lat_min == pytest.approx(45.0)
        assert lat_max == pytest.approx(45.0)
