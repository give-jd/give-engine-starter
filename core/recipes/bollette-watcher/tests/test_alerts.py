"""Tests alerts engine: anomalia consumi/costo + scadenze + persist/dismiss."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from alerts import (  # noqa: E402
    AlertEvent,
    compute_anomalia_consumi,
    compute_anomalia_costo,
    compute_scadenze_imminenti,
    dismiss,
    list_active,
    persist_alert,
    run_periodic_scadenze,
    run_post_import_checks,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript((RECIPE_DIR / "schema.sql").read_text(encoding="utf-8"))
    c.execute(
        "INSERT INTO utenze(alias, tipo, fornitore) VALUES('Casa', 'luce', 'Enel')"
    )
    c.commit()
    return c


def _insert_bolletta(
    con, utenza_id, consumo=None, importo=None, scadenza=None, periodo_inizio=None
):
    cur = con.execute(
        "INSERT INTO bollette(utenza_id, consumo_qta, importo_totale, scadenza, periodo_inizio) "
        "VALUES(?, ?, ?, ?, ?)",
        (utenza_id, consumo, importo, scadenza, periodo_inizio),
    )
    con.commit()
    return cur.lastrowid


class TestAnomaliaConsumi:
    def test_no_alert_under_min_storico(self, conn):
        _insert_bolletta(conn, 1, consumo=100, periodo_inizio="2026-01-01")
        _insert_bolletta(conn, 1, consumo=110, periodo_inizio="2026-02-01")
        new_id = _insert_bolletta(conn, 1, consumo=500, periodo_inizio="2026-03-01")
        assert compute_anomalia_consumi(conn, 1, new_id) is None

    def test_alert_above_soglia(self, conn):
        for i in range(3):
            _insert_bolletta(conn, 1, consumo=100, periodo_inizio=f"2026-0{i + 1}-01")
        new_id = _insert_bolletta(conn, 1, consumo=200, periodo_inizio="2026-04-01")
        ev = compute_anomalia_consumi(conn, 1, new_id)
        assert ev is not None
        assert ev.tipo == "anomalia-consumi"
        assert ev.utenza_id == 1
        assert ev.bolletta_id == new_id
        assert "+" in ev.messaggio

    def test_no_alert_within_soglia(self, conn):
        for i in range(3):
            _insert_bolletta(conn, 1, consumo=100, periodo_inizio=f"2026-0{i + 1}-01")
        new_id = _insert_bolletta(conn, 1, consumo=115, periodo_inizio="2026-04-01")
        assert compute_anomalia_consumi(conn, 1, new_id) is None


class TestAnomaliaCosto:
    def test_alert_above_soglia(self, conn):
        for i in range(3):
            _insert_bolletta(conn, 1, importo=50.0, periodo_inizio=f"2026-0{i + 1}-01")
        new_id = _insert_bolletta(conn, 1, importo=80.0, periodo_inizio="2026-04-01")
        ev = compute_anomalia_costo(conn, 1, new_id)
        assert ev is not None
        assert ev.tipo == "anomalia-costo"
        assert "€" in ev.messaggio


class TestScadenzeImminenti:
    def test_scadenza_entro_giorni(self, conn):
        today = date(2026, 6, 1)
        _insert_bolletta(conn, 1, scadenza="2026-06-04")
        _insert_bolletta(conn, 1, scadenza="2026-07-01")
        events = compute_scadenze_imminenti(conn, today=today, giorni_anticipo=7)
        assert len(events) == 1
        assert events[0].tipo == "scadenza"

    def test_no_alert_se_gia_persistito(self, conn):
        today = date(2026, 6, 1)
        bid = _insert_bolletta(conn, 1, scadenza="2026-06-04")
        persist_alert(
            conn,
            AlertEvent(tipo="scadenza", utenza_id=1, bolletta_id=bid, messaggio="x"),
        )
        events = compute_scadenze_imminenti(conn, today=today, giorni_anticipo=7)
        assert events == []


class TestPersistDismiss:
    def test_persist_and_list_active(self, conn):
        bid = _insert_bolletta(conn, 1, importo=100)
        aid = persist_alert(
            conn,
            AlertEvent(
                tipo="anomalia-costo",
                utenza_id=1,
                bolletta_id=bid,
                messaggio="test alert",
            ),
        )
        assert aid > 0
        active = list_active(conn)
        assert len(active) == 1
        assert active[0]["id"] == aid

    def test_dismiss_hides_from_active(self, conn):
        bid = _insert_bolletta(conn, 1, importo=100)
        aid = persist_alert(
            conn,
            AlertEvent(tipo="scadenza", utenza_id=1, bolletta_id=bid, messaggio="test"),
        )
        dismiss(conn, aid)
        assert list_active(conn) == []


class TestOrchestrators:
    def test_run_post_import_checks_inserts(self, conn):
        for i in range(3):
            _insert_bolletta(
                conn,
                1,
                consumo=100,
                importo=50,
                periodo_inizio=f"2026-0{i + 1}-01",
            )
        new_id = _insert_bolletta(
            conn,
            1,
            consumo=200,
            importo=100,
            periodo_inizio="2026-04-01",
        )
        ids = run_post_import_checks(conn, 1, new_id)
        assert len(ids) == 2
        assert all(i > 0 for i in ids)

    def test_run_periodic_scadenze_inserts(self, conn):
        today = date(2026, 6, 1)
        _insert_bolletta(conn, 1, scadenza="2026-06-04")
        _insert_bolletta(conn, 1, scadenza="2026-06-05")
        ids = run_periodic_scadenze(conn, today=today, giorni_anticipo=7)
        assert len(ids) == 2


class TestDedupHashSchema:
    """Verifica schema W31 ha file_hash UNIQUE INDEX."""

    def test_file_hash_field_exists(self, conn):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bollette)").fetchall()]
        assert "file_hash" in cols

    def test_dedup_unique_index_enforces(self, conn):
        conn.execute(
            "INSERT INTO bollette(utenza_id, file_hash) VALUES(1, ?)", ("abc123",)
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO bollette(utenza_id, file_hash) VALUES(1, ?)",
                ("abc123",),
            )

    def test_null_hash_allowed_multiple(self, conn):
        conn.execute("INSERT INTO bollette(utenza_id, file_hash) VALUES(1, NULL)")
        conn.execute("INSERT INTO bollette(utenza_id, file_hash) VALUES(1, NULL)")
        conn.commit()
