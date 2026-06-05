"""Tests services scadenze-auto-casa."""

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


SCAD_OK = {
    "categoria": "auto",
    "tipo": "bollo",
    "oggetto": "FIAT 500 - AB123CD",
    "prossima_scadenza": "2027-03-15",
    "frequenza_tipo": "annuale",
    "importo_previsto_eur": 180.0,
}


class TestAddScadenza:
    def test_ok(self, conn):
        sid = services.add_scadenza(conn, SCAD_OK)
        assert sid > 0

    def test_categoria_invalida(self, conn):
        with pytest.raises(ValueError, match="categoria"):
            services.add_scadenza(conn, dict(SCAD_OK, categoria="cucina"))

    def test_tipo_obbligatorio(self, conn):
        bad = dict(SCAD_OK)
        del bad["tipo"]
        with pytest.raises(ValueError, match="tipo"):
            services.add_scadenza(conn, bad)

    def test_prossima_scadenza_obbligatoria(self, conn):
        bad = dict(SCAD_OK)
        del bad["prossima_scadenza"]
        with pytest.raises(ValueError, match="prossima_scadenza"):
            services.add_scadenza(conn, bad)

    def test_frequenza_invalida(self, conn):
        with pytest.raises(ValueError, match="frequenza_tipo"):
            services.add_scadenza(conn, dict(SCAD_OK, frequenza_tipo="random"))

    def test_custom_richiede_giorni(self, conn):
        with pytest.raises(ValueError, match="frequenza_custom"):
            services.add_scadenza(conn, dict(SCAD_OK, frequenza_tipo="custom"))

    def test_custom_con_giorni(self, conn):
        sid = services.add_scadenza(conn, dict(SCAD_OK,
                                               frequenza_tipo="custom",
                                               frequenza_custom_giorni=45))
        s = services.get_scadenza(conn, sid)
        assert s["frequenza_tipo"] == "custom"
        assert s["frequenza_custom_giorni"] == 45


class TestListGet:
    def test_list_vuoto(self, conn):
        assert services.list_scadenze(conn) == []

    def test_list_ordinato(self, conn):
        services.add_scadenza(conn, dict(SCAD_OK, prossima_scadenza="2027-12-31"))
        services.add_scadenza(conn, dict(SCAD_OK, prossima_scadenza="2027-01-15"))
        r = services.list_scadenze(conn)
        assert r[0]["prossima_scadenza"] == "2027-01-15"

    def test_list_per_categoria(self, conn):
        services.add_scadenza(conn, dict(SCAD_OK, categoria="auto", tipo="bollo"))
        services.add_scadenza(conn, dict(SCAD_OK, categoria="casa", tipo="IMU"))
        services.add_scadenza(conn, dict(SCAD_OK, categoria="persona", tipo="dentista"))
        assert len(services.list_scadenze(conn, "auto")) == 1
        assert len(services.list_scadenze(conn, "casa")) == 1
        assert len(services.list_scadenze(conn, "persona")) == 1

    def test_categoria_filtro_invalida(self, conn):
        with pytest.raises(ValueError, match="categoria"):
            services.list_scadenze(conn, "xyz")

    def test_get_missing(self, conn):
        assert services.get_scadenza(conn, 9999) is None


class TestUpdate:
    def test_ok(self, conn):
        sid = services.add_scadenza(conn, SCAD_OK)
        services.update_scadenza(conn, sid, {"importo_previsto_eur": 200.0})
        assert services.get_scadenza(conn, sid)["importo_previsto_eur"] == pytest.approx(200.0)

    def test_missing(self, conn):
        with pytest.raises(ValueError, match="non trovata"):
            services.update_scadenza(conn, 9999, {"tipo": "x"})


class TestDelete:
    def test_ok(self, conn):
        sid = services.add_scadenza(conn, SCAD_OK)
        services.delete_scadenza(conn, sid)
        assert services.get_scadenza(conn, sid) is None

    def test_cascade_pagamenti(self, conn):
        sid = services.add_scadenza(conn, SCAD_OK)
        services.registra_pagamento(conn, sid, {"data_pagamento": "2027-03-10"})
        services.delete_scadenza(conn, sid)
        assert services.storico_pagamenti(conn, sid) == []


class TestPagamento:
    def test_registra(self, conn):
        sid = services.add_scadenza(conn, SCAD_OK)
        pid = services.registra_pagamento(conn, sid, {
            "data_pagamento": "2027-03-10",
            "importo_pagato_eur": 180.0,
            "metodo": "bonifico",
        })
        assert pid > 0
        storico = services.storico_pagamenti(conn, sid)
        assert len(storico) == 1
        assert storico[0]["importo_pagato_eur"] == pytest.approx(180.0)

    def test_richiede_data(self, conn):
        sid = services.add_scadenza(conn, SCAD_OK)
        with pytest.raises(ValueError, match="data_pagamento"):
            services.registra_pagamento(conn, sid, {})

    def test_scadenza_inesistente(self, conn):
        with pytest.raises(ValueError, match="non trovata"):
            services.registra_pagamento(conn, 999, {"data_pagamento": "2027-03-10"})

    def test_aggiorna_prossima_scadenza(self, conn):
        sid = services.add_scadenza(conn, dict(SCAD_OK,
                                                prossima_scadenza="2027-03-15",
                                                frequenza_tipo="annuale"))
        services.registra_pagamento(conn, sid, {"data_pagamento": "2027-03-10"})
        nuova = services.get_scadenza(conn, sid)["prossima_scadenza"]
        assert nuova == "2028-03-09"

    def test_una_tantum_non_rinnova(self, conn):
        sid = services.add_scadenza(conn, dict(SCAD_OK,
                                                prossima_scadenza="2027-03-15",
                                                frequenza_tipo="una-tantum"))
        services.registra_pagamento(conn, sid, {"data_pagamento": "2027-03-10"})
        nuova = services.get_scadenza(conn, sid)["prossima_scadenza"]
        assert nuova == "2027-03-15"


class TestRicorrenze:
    @pytest.mark.parametrize("freq,delta_giorni", [
        ("mensile", 30), ("bimestrale", 60), ("trimestrale", 91),
        ("quadrimestrale", 122), ("semestrale", 182), ("annuale", 365),
        ("biennale", 730),
    ])
    def test_calcolo(self, freq, delta_giorni):
        d = date(2026, 1, 1)
        nuova = services.prossima_scadenza_da_ricorrenza(d, freq)
        assert nuova == d + timedelta(days=delta_giorni)

    def test_una_tantum(self):
        assert services.prossima_scadenza_da_ricorrenza(date.today(), "una-tantum") is None

    def test_custom(self):
        d = date(2026, 6, 1)
        nuova = services.prossima_scadenza_da_ricorrenza(d, "custom", 45)
        assert nuova == d + timedelta(days=45)

    def test_custom_senza_giorni(self):
        with pytest.raises(ValueError, match="custom_giorni"):
            services.prossima_scadenza_da_ricorrenza(date.today(), "custom")

    def test_invalida(self):
        with pytest.raises(ValueError, match="frequenza"):
            services.prossima_scadenza_da_ricorrenza(date.today(), "random")


class TestNotifiche:
    def test_in_arrivo(self, conn):
        oggi = date(2027, 3, 1)
        services.add_scadenza(conn, dict(SCAD_OK,
                                          prossima_scadenza="2027-03-10",
                                          giorni_anticipo_notifica=14))
        services.add_scadenza(conn, dict(SCAD_OK,
                                          prossima_scadenza="2027-12-31",
                                          giorni_anticipo_notifica=14))
        arrivo = services.scadenze_in_arrivo(conn, oggi=oggi)
        assert len(arrivo) == 1
        assert arrivo[0]["prossima_scadenza"] == "2027-03-10"

    def test_notifiche_disabilitate(self, conn):
        oggi = date(2027, 3, 1)
        services.add_scadenza(conn, dict(SCAD_OK,
                                          prossima_scadenza="2027-03-10",
                                          notifiche_attive=False))
        assert services.scadenze_in_arrivo(conn, oggi=oggi) == []

    def test_scadute(self, conn):
        oggi = date(2027, 3, 15)
        services.add_scadenza(conn, dict(SCAD_OK, prossima_scadenza="2027-03-01"))
        services.add_scadenza(conn, dict(SCAD_OK, prossima_scadenza="2027-04-01"))
        scadute = services.scadenze_scadute(conn, oggi=oggi)
        assert len(scadute) == 1
        assert scadute[0]["prossima_scadenza"] == "2027-03-01"


class TestDashboard:
    def test_vuoto(self, conn):
        r = services.riepilogo_dashboard(conn)
        assert r["n_scadenze_totali"] == 0
        assert r["per_categoria"] == {"auto": 0, "casa": 0, "persona": 0}
        assert r["spesa_annuale_prevista_eur"] == 0

    def test_popolato(self, conn):
        services.add_scadenza(conn, dict(SCAD_OK, categoria="auto", importo_previsto_eur=180.0))
        services.add_scadenza(conn, dict(SCAD_OK, categoria="casa", importo_previsto_eur=300.0))
        services.add_scadenza(conn, dict(SCAD_OK, categoria="persona", importo_previsto_eur=50.0))
        r = services.riepilogo_dashboard(conn)
        assert r["n_scadenze_totali"] == 3
        assert r["per_categoria"]["auto"] == 1
        assert r["per_categoria"]["casa"] == 1
        assert r["per_categoria"]["persona"] == 1
        assert r["spesa_annuale_prevista_eur"] == pytest.approx(530.0)
