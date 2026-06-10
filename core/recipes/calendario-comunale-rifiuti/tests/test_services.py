"""Test motore ricorrenze + promemoria calendario-comunale-rifiuti."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime
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


def _frazione(conn, nome="Umido"):
    return services.add_frazione(conn, {"nome": nome, "colore": "#6B4423", "icona": "apple"})


# --- prossime_raccolte: settimanale ---


def test_prossime_settimanale_lun_gio(conn):
    fid = _frazione(conn)
    # lunedi (1) e giovedi (4)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "1,4",
    })
    # 2026-06-10 e' un mercoledi. Finestra 7 giorni -> gio 11, lun 15.
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=7)
    date_str = [r["data"] for r in out]
    assert "2026-06-11" in date_str  # giovedi
    assert "2026-06-15" in date_str  # lunedi successivo
    assert all(r["frazione"] == "Umido" for r in out)


def test_prossime_settimanale_solo_finestra(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "3",
    })
    # mercoledi: nei prossimi 3 giorni da mer 10 -> solo il 10 stesso
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=3)
    assert [r["data"] for r in out] == ["2026-06-10"]


# --- prossime_raccolte: quindicinale con parita' ---


def test_prossime_quindicinale_parita(conn):
    fid = _frazione(conn, "Plastica")
    # quindicinale, ancora valido_da = lunedi 2026-06-01, giorno lunedi(1).
    # Settimane attese (parita' su ancora): 01/06, 15/06, 29/06; NON 08/06, 22/06.
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "quindicinale", "giorni_settimana": "1",
        "settimane_alterne": 1, "valido_da": "2026-06-01",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 1), giorni=30)
    date_str = [r["data"] for r in out]
    assert "2026-06-01" in date_str
    assert "2026-06-15" in date_str
    assert "2026-06-29" in date_str
    assert "2026-06-08" not in date_str
    assert "2026-06-22" not in date_str


# --- prossime_raccolte: mensile ---


def test_prossime_mensile_giorno(conn):
    fid = _frazione(conn, "Ingombranti")
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "mensile", "giorno_mese": 20,
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 1), giorni=40)
    date_str = [r["data"] for r in out]
    assert "2026-06-20" in date_str


# --- prossime_raccolte: lista_date ---


def test_prossime_lista_date(conn):
    fid = _frazione(conn, "RAEE")
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "lista_date",
        "date_extra": "2026-06-12,2026-07-12,2026-08-12",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 1), giorni=45)
    date_str = [r["data"] for r in out]
    assert "2026-06-12" in date_str
    assert "2026-07-12" in date_str
    assert "2026-08-12" not in date_str  # fuori finestra 45gg


# --- eccezioni: salta e sposta ---


def test_eccezione_salta(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    # giovedi 11/06 saltato (festivita')
    services.add_eccezione(conn, {
        "data": "2026-06-11", "frazione_id": fid, "salta": True, "motivo": "festa",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=7)
    assert "2026-06-11" not in [r["data"] for r in out]


def test_eccezione_sposta(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    # giovedi 11/06 spostato a venerdi 12/06
    services.add_eccezione(conn, {
        "data": "2026-06-11", "frazione_id": fid, "salta": False,
        "sposta_a": "2026-06-12", "motivo": "variazione",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=7)
    date_str = [r["data"] for r in out]
    assert "2026-06-11" not in date_str
    assert "2026-06-12" in date_str


# --- validazioni ---


def test_ricorrenza_settimanale_senza_giorni_errore(conn):
    fid = _frazione(conn)
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {"frazione_id": fid, "tipo": "settimanale"})


def test_ricorrenza_quindicinale_senza_ancora_errore(conn):
    fid = _frazione(conn)
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {
            "frazione_id": fid, "tipo": "quindicinale", "giorni_settimana": "1",
        })


def test_ricorrenza_tipo_sconosciuto_errore(conn):
    fid = _frazione(conn)
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {"frazione_id": fid, "tipo": "boh"})


def test_ricorrenza_mensile_senza_giorno_errore(conn):
    fid = _frazione(conn)
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {"frazione_id": fid, "tipo": "mensile"})


def test_ricorrenza_lista_date_senza_date_errore(conn):
    fid = _frazione(conn)
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {"frazione_id": fid, "tipo": "lista_date"})


# --- promemoria_da_inviare: anticipo + dedup ---


def test_promemoria_entro_anticipo(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    services.add_promemoria(conn, {"frazione_id": fid, "anticipo_ore": 24})
    # now = mer 10/06 18:00; raccolta gio 11/06 -> entro 24h
    now = datetime(2026, 6, 10, 18, 0)
    out = services.promemoria_da_inviare(conn, now=now)
    assert any(r["frazione"] == "Umido" for r in out)


def test_promemoria_fuori_anticipo(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "1",
    })
    services.add_promemoria(conn, {"frazione_id": fid, "anticipo_ore": 12})
    # now = mer 10/06; prossimo lunedi 15/06, ben oltre 12h
    now = datetime(2026, 6, 10, 9, 0)
    out = services.promemoria_da_inviare(conn, now=now)
    assert out == []


def test_promemoria_dedup_giornaliera(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    pid = services.add_promemoria(conn, {"frazione_id": fid, "anticipo_ore": 24})
    now = datetime(2026, 6, 10, 18, 0)
    out1 = services.promemoria_da_inviare(conn, now=now)
    assert out1
    services.marca_promemoria_inviato(conn, pid, now.date())
    out2 = services.promemoria_da_inviare(conn, now=now)
    assert out2 == []


# --- cerca_materiale ---


def test_cerca_materiale_match(conn):
    fid = _frazione(conn)
    services.add_voce_regolamento(conn, {"materiale": "bucce di banana", "frazione_id": fid})
    out = services.cerca_materiale(conn, "banana")
    assert out
    assert out[0]["materiale"] == "bucce di banana"
    assert out[0]["frazione"] == "Umido"


def test_cerca_materiale_miss(conn):
    fid = _frazione(conn)
    services.add_voce_regolamento(conn, {"materiale": "bucce di banana", "frazione_id": fid})
    out = services.cerca_materiale(conn, "plutonio")
    assert out == []
