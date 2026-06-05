"""Test integrazione letture-contatori ⇄ bollette-watcher."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE_DIR))
import app  # noqa: E402


def _make_bollette_db(path: Path) -> None:
    bc = sqlite3.connect(str(path))
    bc.executescript(
        """
        CREATE TABLE utenze (
          id INTEGER PRIMARY KEY, alias TEXT, tipo TEXT,
          fornitore TEXT, pod_pdr TEXT, intestatario TEXT);
        CREATE TABLE bollette (
          id INTEGER PRIMARY KEY, utenza_id INTEGER,
          lettura_prec REAL, lettura_prec_data TEXT,
          lettura_att REAL, lettura_att_data TEXT, consumo_unita TEXT);
        """
    )
    bc.execute("INSERT INTO utenze (id, alias, tipo, fornitore, pod_pdr) "
               "VALUES (1, 'Casa', 'gas', 'AGN Energia', '62604597')")
    bc.execute(
        "INSERT INTO bollette (utenza_id, lettura_prec, lettura_prec_data, "
        "lettura_att, lettura_att_data, consumo_unita) "
        "VALUES (1, 721, '2025-08-27', 1063, '2026-02-28', 'Smc')")
    bc.commit()
    bc.close()


@pytest.fixture
def letture_conn():
    c = sqlite3.connect(":memory:")
    c.executescript((RECIPE_DIR / "schema.sql").read_text())
    c.row_factory = sqlite3.Row
    return c


def test_read_bollette_readings(tmp_path, monkeypatch):
    db = tmp_path / "bollette-watcher.db"
    _make_bollette_db(db)
    monkeypatch.setattr(app, "BOLLETTE_DB", db)
    out = app.read_bollette_readings()
    # 2 letture assolute (prec + att), ordinate per data
    assert [r["valore"] for r in out] == [721.0, 1063.0]
    assert out[0]["data"] == "2025-08-27"
    assert out[1]["data"] == "2026-02-28"
    assert out[0]["tipo"] == "gas"
    assert out[0]["pod_pdr"] == "62604597"


def test_read_bollette_readings_no_db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BOLLETTE_DB", tmp_path / "assente.db")
    assert app.read_bollette_readings() == []


def test_read_bollette_readings_old_schema(tmp_path, monkeypatch):
    db = tmp_path / "bollette-watcher.db"
    bc = sqlite3.connect(str(db))
    bc.executescript("CREATE TABLE bollette (id INTEGER PRIMARY KEY, utenza_id INTEGER);")
    bc.close()
    monkeypatch.setattr(app, "BOLLETTE_DB", db)
    assert app.read_bollette_readings() == []


def test_match_utenza_by_pod(letture_conn):
    app.add_utenza(letture_conn, "gas", "62604597", "AGN", "Casa", False)
    utenze = app.list_utenze(letture_conn)
    cand = {"tipo": "gas", "pod_pdr": "62604597"}
    assert app._match_utenza(cand, utenze) == utenze[0]["id"]


def test_match_utenza_fallback_unico_tipo(letture_conn):
    app.add_utenza(letture_conn, "gas", "ALTRO", "AGN", "Casa", False)
    utenze = app.list_utenze(letture_conn)
    cand = {"tipo": "gas", "pod_pdr": ""}
    assert app._match_utenza(cand, utenze) == utenze[0]["id"]


def test_match_utenza_ambiguo_ritorna_none(letture_conn):
    app.add_utenza(letture_conn, "gas", "A", "AGN", "Casa1", False)
    app.add_utenza(letture_conn, "gas", "B", "AGN", "Casa2", False)
    utenze = app.list_utenze(letture_conn)
    cand = {"tipo": "gas", "pod_pdr": "X"}
    assert app._match_utenza(cand, utenze) is None


def test_read_bollette_utenze_filtra_non_contatore(tmp_path, monkeypatch):
    db = tmp_path / "bollette-watcher.db"
    bc = sqlite3.connect(str(db))
    bc.executescript(
        "CREATE TABLE utenze (id INTEGER PRIMARY KEY, alias TEXT, tipo TEXT, "
        "fornitore TEXT, pod_pdr TEXT);")
    bc.execute("INSERT INTO utenze (alias,tipo,fornitore,pod_pdr) VALUES "
               "('Casa gas','gas','AGN','62604597')")
    bc.execute("INSERT INTO utenze (alias,tipo,fornitore,pod_pdr) VALUES "
               "('Casa luce','luce','Enel','IT001E')")
    bc.execute("INSERT INTO utenze (alias,tipo,fornitore,pod_pdr) VALUES "
               "('Mobile','telefono','TIM',NULL)")
    bc.commit()
    bc.close()
    monkeypatch.setattr(app, "BOLLETTE_DB", db)
    out = app.read_bollette_utenze()
    tipi = sorted(u["tipo"] for u in out)
    assert tipi == ["gas", "luce"]  # telefono escluso


def test_read_bollette_utenze_no_db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "BOLLETTE_DB", tmp_path / "assente.db")
    assert app.read_bollette_utenze() == []


def test_read_scadenze_auto_casa(tmp_path, monkeypatch):
    db = tmp_path / "scadenze-auto-casa.db"
    sc = sqlite3.connect(str(db))
    sc.executescript(
        "CREATE TABLE scadenze (id INTEGER PRIMARY KEY, categoria TEXT, tipo TEXT, "
        "oggetto TEXT, prossima_scadenza DATE, importo_previsto_eur REAL);")
    sc.execute("INSERT INTO scadenze (categoria,tipo,oggetto,prossima_scadenza,importo_previsto_eur) "
               "VALUES ('casa','Bollo','Caldaia','2026-09-01',128.0)")
    sc.commit()
    sc.close()
    monkeypatch.setattr(app, "SCADENZE_DB", db)
    out = app.read_scadenze_auto_casa()
    assert len(out) == 1
    assert out[0]["categoria"] == "casa"
    assert out[0]["prossima_scadenza"] == "2026-09-01"


def test_read_scadenze_auto_casa_no_db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SCADENZE_DB", tmp_path / "assente.db")
    assert app.read_scadenze_auto_casa() == []


def test_import_dedup(letture_conn):
    app.add_utenza(letture_conn, "gas", "62604597", "AGN", "Casa", False)
    uid = app.list_utenze(letture_conn)[0]["id"]
    app.add_lettura_fattura(letture_conn, uid, "2026-02-28", 1063.0)
    assert app.lettura_exists(letture_conn, uid, "2026-02-28") is True
    assert app.lettura_exists(letture_conn, uid, "2025-08-27") is False
