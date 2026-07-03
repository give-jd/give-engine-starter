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


# --- validazioni CRUD mancanti ---


def test_frazione_senza_nome_errore(conn):
    with pytest.raises(ValueError):
        services.add_frazione(conn, {})


def test_ricorrenza_senza_frazione_errore(conn):
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {"tipo": "settimanale", "giorni_settimana": "1"})


def test_ricorrenza_giorno_fuori_range_errore(conn):
    fid = _frazione(conn)
    with pytest.raises(ValueError):
        services.add_ricorrenza(conn, {
            "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "8",
        })


def test_eccezione_senza_data_errore(conn):
    with pytest.raises(ValueError):
        services.add_eccezione(conn, {"salta": True})


def test_eccezione_senza_salta_ne_sposta_errore(conn):
    with pytest.raises(ValueError):
        services.add_eccezione(conn, {"data": "2026-06-11"})


def test_voce_regolamento_senza_materiale_errore(conn):
    with pytest.raises(ValueError):
        services.add_voce_regolamento(conn, {})


def test_promemoria_senza_frazione_errore(conn):
    with pytest.raises(ValueError):
        services.add_promemoria(conn, {})


# --- delete + list ---


def test_delete_frazione_cascade(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "1",
    })
    services.delete_frazione(conn, fid)
    assert services.get_frazione(conn, fid) is None
    assert services.list_ricorrenze(conn) == []


def test_delete_ricorrenza_e_list_filtrato(conn):
    fid = _frazione(conn)
    rid = services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "1",
    })
    assert len(services.list_ricorrenze(conn, frazione_id=fid)) == 1
    services.delete_ricorrenza(conn, rid)
    assert services.list_ricorrenze(conn, frazione_id=fid) == []


def test_list_promemoria_con_nome_frazione(conn):
    fid = _frazione(conn)
    services.add_promemoria(conn, {"frazione_id": fid, "anticipo_ore": 6})
    out = services.list_promemoria(conn)
    assert len(out) == 1
    assert out[0]["frazione"] == "Umido"


# --- motore: rami residui ---


def test_ricorrenza_fuori_validita(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
        "valido_da": "2026-07-01",  # inizia dopo la finestra
    })
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "3",
        "valido_a": "2026-06-01",  # finita prima della finestra
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=7)
    assert out == []


def test_lista_date_token_vuoto_ignorato(conn):
    fid = _frazione(conn, "RAEE")
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "lista_date",
        "date_extra": "2026-06-12, ,2026-06-20,",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=15)
    assert [r["data"] for r in out] == ["2026-06-12", "2026-06-20"]


def test_mensile_giorno_31_salta_mesi_corti(conn):
    fid = _frazione(conn, "Ingombranti")
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "mensile", "giorno_mese": 31,
    })
    # giugno ha 30 giorni: nessuna occorrenza a giugno, si' il 31 luglio
    out = services.prossime_raccolte(conn, da=date(2026, 6, 1), giorni=61)
    assert [r["data"] for r in out] == ["2026-07-31"]


def test_mensile_attraversa_dicembre(conn):
    fid = _frazione(conn, "Ingombranti")
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "mensile", "giorno_mese": 15,
    })
    out = services.prossime_raccolte(conn, da=date(2026, 12, 1), giorni=50)
    date_str = [r["data"] for r in out]
    assert "2026-12-15" in date_str
    assert "2027-01-15" in date_str


def test_eccezione_altra_frazione_non_applicata(conn):
    fid = _frazione(conn)
    altro = _frazione(conn, "Vetro")
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    # eccezioni su data diversa e su frazione diversa: nessun effetto
    services.add_eccezione(conn, {"data": "2026-06-18", "salta": True})
    services.add_eccezione(conn, {
        "data": "2026-06-11", "frazione_id": altro, "salta": True,
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=7)
    assert "2026-06-11" in [r["data"] for r in out]


def test_eccezione_sposta_fuori_finestra(conn):
    fid = _frazione(conn)
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    services.add_eccezione(conn, {
        "data": "2026-06-11", "frazione_id": fid, "salta": False,
        "sposta_a": "2026-08-01",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=3)
    assert out == []


def test_frazione_disattivata_esclusa(conn):
    fid = services.add_frazione(conn, {"nome": "Vetro", "attiva": False})
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=7)
    assert out == []


def test_dedup_stessa_frazione_stessa_data(conn):
    fid = _frazione(conn)
    for _ in range(2):  # due ricorrenze che producono la stessa data
        services.add_ricorrenza(conn, {
            "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
        })
    out = services.prossime_raccolte(conn, da=date(2026, 6, 10), giorni=3)
    assert [r["data"] for r in out] == ["2026-06-11"]


def test_promemoria_frazione_senza_raccolta_vicina(conn):
    fid = _frazione(conn)
    vetro = _frazione(conn, "Vetro")
    # raccolta imminente solo per Umido; promemoria attivo solo su Vetro
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale", "giorni_settimana": "4",
    })
    services.add_promemoria(conn, {"frazione_id": vetro, "anticipo_ore": 24})
    out = services.promemoria_da_inviare(conn, now=datetime(2026, 6, 10, 18, 0))
    assert out == []
