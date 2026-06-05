"""Tests services letture-contatori."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
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


class TestUtenze:
    def test_add_gas_default_um(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas", "alias_utente": "Casa"})
        u = services.get_utenza(conn, uid)
        assert u["unita_misura"] == "Smc"

    def test_add_luce_default_um(self, conn):
        uid = services.add_utenza(conn, {"tipo": "luce"})
        u = services.get_utenza(conn, uid)
        assert u["unita_misura"] == "kWh"

    def test_add_acqua_default_um(self, conn):
        uid = services.add_utenza(conn, {"tipo": "acqua"})
        u = services.get_utenza(conn, uid)
        assert u["unita_misura"] == "mc"

    def test_tipo_invalido(self, conn):
        with pytest.raises(ValueError, match="tipo"):
            services.add_utenza(conn, {"tipo": "internet"})

    def test_list_tutte(self, conn):
        services.add_utenza(conn, {"tipo": "gas"})
        services.add_utenza(conn, {"tipo": "luce"})
        assert len(services.list_utenze(conn)) == 2

    def test_list_filtro_tipo(self, conn):
        services.add_utenza(conn, {"tipo": "gas"})
        services.add_utenza(conn, {"tipo": "luce"})
        gas = services.list_utenze(conn, "gas")
        assert len(gas) == 1
        assert gas[0]["tipo"] == "gas"

    def test_get_missing(self, conn):
        assert services.get_utenza(conn, 999) is None

    def test_delete_cascade_letture(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0})
        services.delete_utenza(conn, uid)
        assert services.list_letture(conn, uid) == []


class TestLetture:
    def test_add(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        lid = services.add_lettura(conn, {
            "utenza_id": uid, "valore": 1234.5,
            "data_lettura": "2026-05-30",
        })
        assert lid > 0

    def test_default_data_oggi(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0})
        letture = services.list_letture(conn, uid)
        assert letture[0]["data_lettura"] == date.today().isoformat()

    def test_richiede_utenza(self, conn):
        with pytest.raises(ValueError, match="utenza_id"):
            services.add_lettura(conn, {"valore": 100.0})

    def test_richiede_valore(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        with pytest.raises(ValueError, match="valore"):
            services.add_lettura(conn, {"utenza_id": uid})

    def test_valore_negativo_rifiutato(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        with pytest.raises(ValueError, match="negativo"):
            services.add_lettura(conn, {"utenza_id": uid, "valore": -1.0})

    def test_tipo_lettura_invalido(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        with pytest.raises(ValueError, match="tipo_lettura"):
            services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0,
                                        "tipo_lettura": "xyz"})

    def test_fasce_orarie(self, conn):
        uid = services.add_utenza(conn, {"tipo": "luce", "fasce_orarie_attive": True})
        lid = services.add_lettura(conn, {
            "utenza_id": uid, "valore": 100.0,
            "valore_f1": 40.0, "valore_f2": 35.0, "valore_f3": 25.0,
        })
        letture = services.list_letture(conn, uid)
        assert letture[0]["valore_f1"] == pytest.approx(40.0)
        assert letture[0]["valore_f3"] == pytest.approx(25.0)
        assert lid > 0

    def test_list_ordinato_desc(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0, "data_lettura": "2026-01-01"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 150.0, "data_lettura": "2026-05-01"})
        letture = services.list_letture(conn, uid)
        assert letture[0]["data_lettura"] == "2026-05-01"

    def test_ultima_lettura(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0, "data_lettura": "2026-01-01"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 150.0, "data_lettura": "2026-05-01"})
        u = services.ultima_lettura(conn, uid)
        assert u["valore"] == pytest.approx(150.0)

    def test_ultima_lettura_vuota(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        assert services.ultima_lettura(conn, uid) is None


class TestConsumi:
    def test_consumo_periodo(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0, "data_lettura": "2026-01-01"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 250.0, "data_lettura": "2026-05-01"})
        r = services.consumo_periodo(conn, uid, "2026-01-01", "2026-12-31")
        assert r["consumo"] == pytest.approx(150.0)
        assert r["n_letture"] == 2
        assert r["giorni"] == 120

    def test_consumo_giornaliero_medio(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 0.0, "data_lettura": "2026-01-01"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0, "data_lettura": "2026-01-11"})
        r = services.consumo_periodo(conn, uid, "2026-01-01", "2026-01-31")
        assert r["consumo_giornaliero_medio"] == pytest.approx(10.0)

    def test_consumo_solo_una_lettura(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0, "data_lettura": "2026-01-01"})
        r = services.consumo_periodo(conn, uid, "2026-01-01", "2026-12-31")
        assert r["consumo"] is None
        assert r["n_letture"] == 1

    def test_consumo_zero_letture(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        r = services.consumo_periodo(conn, uid, "2026-01-01", "2026-12-31")
        assert r["consumo"] is None
        assert r["n_letture"] == 0


class TestFinestre:
    def test_add(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        fid = services.add_finestra(conn, uid, "2026-05", 25, 31)
        assert fid > 0

    def test_invalid_giorno_inizio(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        with pytest.raises(ValueError, match="giorno_inizio"):
            services.add_finestra(conn, uid, "2026-05", 0, 31)

    def test_invalid_giorno_fine(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        with pytest.raises(ValueError, match="giorno_fine"):
            services.add_finestra(conn, uid, "2026-05", 1, 32)

    def test_fine_minore_inizio(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        with pytest.raises(ValueError, match="giorno_fine"):
            services.add_finestra(conn, uid, "2026-05", 25, 20)

    def test_finestra_aperta_oggi(self, conn):
        oggi = date(2026, 5, 28)
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_finestra(conn, uid, oggi.strftime("%Y-%m"), 25, 31)
        aperte = services.finestre_aperte(conn, oggi=oggi)
        assert len(aperte) == 1

    def test_finestra_chiusa(self, conn):
        oggi = date(2026, 5, 28)
        uid = services.add_utenza(conn, {"tipo": "gas"})
        fid = services.add_finestra(conn, uid, oggi.strftime("%Y-%m"), 25, 31)
        services.chiudi_finestra(conn, fid)
        aperte = services.finestre_aperte(conn, oggi=oggi)
        assert len(aperte) == 0

    def test_finestra_fuori_data(self, conn):
        oggi = date(2026, 5, 10)
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_finestra(conn, uid, oggi.strftime("%Y-%m"), 25, 31)
        aperte = services.finestre_aperte(conn, oggi=oggi)
        assert len(aperte) == 0


class TestDashboard:
    def test_vuoto(self, conn):
        r = services.riepilogo_dashboard(conn)
        assert r["n_utenze"] == 0
        assert r["n_letture_ultimo_anno"] == 0

    def test_popolato(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0})
        r = services.riepilogo_dashboard(conn)
        assert r["n_utenze"] == 1
        assert r["n_letture_ultimo_anno"] == 1

    def test_letture_vecchie_escluse(self, conn):
        uid = services.add_utenza(conn, {"tipo": "gas"})
        old_date = (date.today() - timedelta(days=400)).isoformat()
        services.add_lettura(conn, {"utenza_id": uid, "valore": 100.0,
                                    "data_lettura": old_date})
        r = services.riepilogo_dashboard(conn)
        assert r["n_letture_ultimo_anno"] == 0
