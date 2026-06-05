"""Tests services osservaprezzi-carburanti."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from modules import services  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    services.init_db(c)
    yield c
    c.close()


DIST_OK = {
    "id": 12345, "bandiera": "Eni", "tipo_impianto": "Stradale",
    "nome_impianto": "Milano Duomo", "comune": "Milano", "provincia": "MI",
    "latitudine": 45.4642, "longitudine": 9.1900,
}


class TestDistributori:
    def test_upsert(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        d = services.get_distributore(conn, 12345)
        assert d["bandiera"] == "Eni"
        assert d["comune"] == "Milano"

    def test_upsert_replace(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        services.upsert_distributore(conn, dict(DIST_OK, bandiera="Esso"))
        d = services.get_distributore(conn, 12345)
        assert d["bandiera"] == "Esso"

    def test_id_obbligatorio(self, conn):
        bad = dict(DIST_OK)
        del bad["id"]
        with pytest.raises(ValueError, match="id"):
            services.upsert_distributore(conn, bad)

    def test_get_missing(self, conn):
        assert services.get_distributore(conn, 999) is None

    def test_search_per_comune(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        services.upsert_distributore(conn, dict(DIST_OK, id=99999, comune="Torino"))
        r = services.search_distributori(conn, "Milano")
        assert len(r) == 1
        assert r[0]["comune"] == "Milano"


class TestPrezzi:
    def test_aggiorna(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        pid = services.aggiorna_prezzo(conn, 12345, {
            "carburante": "Benzina", "prezzo_self": 1.795,
            "data_comunicazione": "2026-05-25T08:00:00",
        })
        assert pid > 0
        p = services.ultimo_prezzo(conn, 12345, "Benzina")
        assert p["prezzo_self"] == pytest.approx(1.795)

    def test_carburante_invalido(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        with pytest.raises(ValueError, match="carburante"):
            services.aggiorna_prezzo(conn, 12345, {
                "carburante": "Idrogeno", "prezzo_self": 1.5,
                "data_comunicazione": "2026-05-25T08:00:00",
            })

    def test_prezzo_negativo(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        with pytest.raises(ValueError, match="positivo"):
            services.aggiorna_prezzo(conn, 12345, {
                "carburante": "Benzina", "prezzo_self": -1.0,
                "data_comunicazione": "2026-05-25T08:00:00",
            })

    def test_almeno_un_prezzo(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        with pytest.raises(ValueError, match="almeno uno"):
            services.aggiorna_prezzo(conn, 12345, {
                "carburante": "Benzina",
                "data_comunicazione": "2026-05-25T08:00:00",
            })

    def test_ultimo_prezzo_vuoto(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        assert services.ultimo_prezzo(conn, 12345, "Benzina") is None

    def test_data_comunicazione_obbligatoria(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        with pytest.raises(ValueError, match="data_comunicazione"):
            services.aggiorna_prezzo(conn, 12345, {
                "carburante": "Benzina", "prezzo_self": 1.8,
            })


class TestPreferiti:
    def test_add(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        pid = services.add_preferito(conn, 12345, etichetta="Casa",
                                      alert_sotto_eur=1.75)
        assert pid > 0
        prefs = services.list_preferiti(conn)
        assert len(prefs) == 1
        assert prefs[0]["etichetta_utente"] == "Casa"

    def test_distributore_inesistente(self, conn):
        with pytest.raises(ValueError, match="distributore"):
            services.add_preferito(conn, 999)

    def test_carburante_invalido(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        with pytest.raises(ValueError, match="carburante"):
            services.add_preferito(conn, 12345, carburante_principale="Idrogeno")

    def test_in_alert(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        services.aggiorna_prezzo(conn, 12345, {
            "carburante": "Benzina", "prezzo_self": 1.70,
            "data_comunicazione": "2026-05-25T08:00:00",
        })
        services.add_preferito(conn, 12345, alert_sotto_eur=1.75)
        alert = services.preferiti_in_alert(conn)
        assert len(alert) == 1

    def test_non_in_alert(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        services.aggiorna_prezzo(conn, 12345, {
            "carburante": "Benzina", "prezzo_self": 1.80,
            "data_comunicazione": "2026-05-25T08:00:00",
        })
        services.add_preferito(conn, 12345, alert_sotto_eur=1.75)
        assert services.preferiti_in_alert(conn) == []

    def test_rimuovi(self, conn):
        services.upsert_distributore(conn, DIST_OK)
        pid = services.add_preferito(conn, 12345)
        services.rimuovi_preferito(conn, pid)
        assert services.list_preferiti(conn) == []


class TestRifornimenti:
    def test_add_calcola_totale(self, conn):
        rid = services.add_rifornimento(conn, {
            "data": "2026-05-25", "carburante": "Benzina",
            "litri": 30.0, "prezzo_unitario": 1.795,
        })
        assert rid > 0
        r = services.list_rifornimenti(conn)[0]
        assert r["prezzo_totale"] == pytest.approx(53.85)

    def test_litri_obbligatori(self, conn):
        with pytest.raises(ValueError, match="litri"):
            services.add_rifornimento(conn, {
                "data": "2026-05-25", "carburante": "Benzina",
                "prezzo_unitario": 1.795,
            })

    def test_litri_negativi(self, conn):
        with pytest.raises(ValueError, match="litri"):
            services.add_rifornimento(conn, {
                "data": "2026-05-25", "carburante": "Benzina",
                "litri": -10.0, "prezzo_unitario": 1.795,
            })

    def test_carburante_invalido(self, conn):
        with pytest.raises(ValueError, match="carburante"):
            services.add_rifornimento(conn, {
                "data": "2026-05-25", "carburante": "Idrogeno",
                "litri": 30.0, "prezzo_unitario": 5.0,
            })

    def test_prezzo_unitario_obbligatorio(self, conn):
        with pytest.raises(ValueError, match="prezzo_unitario"):
            services.add_rifornimento(conn, {
                "data": "2026-05-25", "carburante": "Benzina",
                "litri": 30.0,
            })

    def test_data_obbligatoria(self, conn):
        with pytest.raises(ValueError, match="data"):
            services.add_rifornimento(conn, {
                "carburante": "Benzina", "litri": 30.0, "prezzo_unitario": 1.8,
            })

    def test_list_per_anno(self, conn):
        services.add_rifornimento(conn, {
            "data": "2026-05-25", "carburante": "Benzina",
            "litri": 30.0, "prezzo_unitario": 1.795,
        })
        services.add_rifornimento(conn, {
            "data": "2025-12-15", "carburante": "Benzina",
            "litri": 25.0, "prezzo_unitario": 1.70,
        })
        assert len(services.list_rifornimenti(conn, anno=2026)) == 1
        assert len(services.list_rifornimenti(conn, anno=2025)) == 1


class TestConsumoMedio:
    def test_vuoto(self, conn):
        r = services.consumo_medio(conn)
        assert r["consumo_l_per_100km"] is None

    def test_una_lettura(self, conn):
        services.add_rifornimento(conn, {
            "data": "2026-05-25", "carburante": "Benzina",
            "litri": 30.0, "prezzo_unitario": 1.8, "km_attuali": 50000,
        })
        r = services.consumo_medio(conn)
        assert r["consumo_l_per_100km"] is None
        assert r["n_rifornimenti"] == 1

    def test_calcolo(self, conn):
        services.add_rifornimento(conn, {
            "data": "2026-01-01", "carburante": "Benzina",
            "litri": 30.0, "prezzo_unitario": 1.8, "km_attuali": 50000,
        })
        services.add_rifornimento(conn, {
            "data": "2026-05-01", "carburante": "Benzina",
            "litri": 40.0, "prezzo_unitario": 1.85, "km_attuali": 50800,
        })
        r = services.consumo_medio(conn)
        assert r["km_totali"] == 800
        assert r["consumo_l_per_100km"] == pytest.approx(5.0)


class TestRefreshMimit:
    def test_log_ok(self, conn):
        rid = services.log_refresh_mimit(conn, "OK",
                                          righe_anagrafica=23000,
                                          righe_prezzi=46000)
        assert rid > 0
        u = services.ultimo_refresh(conn)
        assert u["esito"] == "OK"
        assert u["righe_anagrafica"] == 23000

    def test_log_fail_con_note(self, conn):
        services.log_refresh_mimit(conn, "FAIL", note="Timeout MIMIT")
        u = services.ultimo_refresh(conn)
        assert u["esito"] == "FAIL"
        assert "Timeout" in u["note"]

    def test_ultimo_vuoto(self, conn):
        assert services.ultimo_refresh(conn) is None
