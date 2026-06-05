"""Tests export CSV bollette + alerts + deducibili."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from exports import (  # noqa: E402
    export_csv_alerts,
    export_csv_bollette,
    export_csv_deducibili,
    generate_filename,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript((RECIPE_DIR / "schema.sql").read_text(encoding="utf-8"))
    c.execute(
        "INSERT INTO utenze(alias, tipo, fornitore, pod_pdr) "
        "VALUES('Casa Luce', 'luce', 'Enel', 'IT001E12345678901')"
    )
    c.execute(
        "INSERT INTO utenze(alias, tipo, fornitore, pod_pdr) "
        "VALUES('Casa Gas', 'gas', 'Eni', '12345678901234')"
    )
    for mese in (1, 2, 3):
        c.execute(
            "INSERT INTO bollette(utenza_id, periodo_inizio, periodo_fine, "
            "consumo_qta, consumo_unita, importo_totale, iva, scadenza, "
            "parser_usato, confidence) "
            "VALUES(1, ?, ?, 200, 'kWh', 65.50, 11.80, ?, 'enel', 0.95)",
            (
                f"2026-0{mese}-01",
                f"2026-0{mese}-28",
                f"2026-0{mese + 1:02d}-15",
            ),
        )
    c.execute(
        "INSERT INTO bollette(utenza_id, periodo_inizio, importo_totale, "
        "parser_usato, confidence) "
        "VALUES(1, '2025-12-01', 50.00, 'enel', 0.9)"
    )
    c.commit()
    return c


class TestExportBollette:
    def test_export_all_bollette(self, conn, tmp_path):
        out = tmp_path / "bollette.csv"
        n = export_csv_bollette(conn, out)
        assert n == 4
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("﻿")
        assert "Casa Luce" in content
        assert "Enel" in content

    def test_filter_by_anno(self, conn, tmp_path):
        out = tmp_path / "bollette_2026.csv"
        n = export_csv_bollette(conn, out, anno=2026)
        assert n == 3
        content = out.read_text(encoding="utf-8")
        assert "2025-12-01" not in content

    def test_filter_by_utenza(self, conn, tmp_path):
        out = tmp_path / "luce.csv"
        n = export_csv_bollette(conn, out, utenza_id=1)
        assert n == 4

    def test_filter_anno_and_utenza(self, conn, tmp_path):
        out = tmp_path / "luce_2026.csv"
        n = export_csv_bollette(conn, out, anno=2026, utenza_id=1)
        assert n == 3


class TestExportAlerts:
    def test_export_active_only(self, conn, tmp_path):
        conn.execute(
            "INSERT INTO alert(utenza_id, bolletta_id, tipo, messaggio) "
            "VALUES(1, 1, 'anomalia-costo', 'test active')"
        )
        conn.execute(
            "INSERT INTO alert(utenza_id, bolletta_id, tipo, messaggio, dismissed_at) "
            "VALUES(1, 2, 'scadenza', 'test dismissed', datetime('now'))"
        )
        conn.commit()
        out = tmp_path / "alerts.csv"
        n = export_csv_alerts(conn, out, include_dismissed=False)
        assert n == 1

    def test_export_include_dismissed(self, conn, tmp_path):
        conn.execute(
            "INSERT INTO alert(utenza_id, bolletta_id, tipo, messaggio) "
            "VALUES(1, 1, 'anomalia-costo', 'a1')"
        )
        conn.execute(
            "INSERT INTO alert(utenza_id, bolletta_id, tipo, messaggio, dismissed_at) "
            "VALUES(1, 2, 'scadenza', 'a2', datetime('now'))"
        )
        conn.commit()
        out = tmp_path / "alerts_all.csv"
        n = export_csv_alerts(conn, out, include_dismissed=True)
        assert n == 2


class TestExportDeducibili:
    def test_deducibili_quota_30(self, conn, tmp_path):
        out = tmp_path / "deducibili.csv"
        n = export_csv_deducibili(conn, out, anno=2026, quota_studio_perc=0.30)
        assert n == 1
        content = out.read_text(encoding="utf-8")
        # Totale 2026 = 65.50 * 3 = 196.50, deducibile = 58.95
        assert "58.95" in content

    def test_deducibili_quota_zero(self, conn, tmp_path):
        out = tmp_path / "deducibili_0.csv"
        n = export_csv_deducibili(conn, out, anno=2026, quota_studio_perc=0.0)
        assert n == 1

    def test_quota_out_of_range_raises(self, conn, tmp_path):
        with pytest.raises(ValueError):
            export_csv_deducibili(
                conn, tmp_path / "x.csv", anno=2026, quota_studio_perc=1.5
            )
        with pytest.raises(ValueError):
            export_csv_deducibili(
                conn, tmp_path / "x.csv", anno=2026, quota_studio_perc=-0.1
            )


class TestGenerateFilename:
    def test_with_anno(self):
        name = generate_filename("bollette", anno=2026)
        assert name.startswith("bollette_2026_export-")
        assert name.endswith(".csv")

    def test_without_anno(self):
        name = generate_filename("alerts")
        assert name.startswith("alerts_export-")
        assert name.endswith(".csv")
