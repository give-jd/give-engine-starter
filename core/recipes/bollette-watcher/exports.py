"""Export CSV per commercialista / dichiarazione redditi.

Categorie export:
- export_csv_bollette: tutte bollette + utenza details (CSV principale)
- export_csv_alerts: storico alert attivi + dismissed
- export_csv_deducibili: utenze contrassegnate detraibili pro-quota studio

Format CSV: RFC 4180 con UTF-8 BOM (compatibilità Excel italiano).
Separatore: virgola (default RFC). Quote: doppia se field contiene "," o newline.
Date: ISO 8601 (YYYY-MM-DD). Decimal: punto separatore (numeric).
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path


# UTF-8 BOM per compatibilità Excel IT (auto-detect encoding)
_UTF8_BOM = "﻿"


def _write_csv(path: Path, headers: list[str], rows: list[list]) -> None:
    """Helper: scrive CSV con UTF-8 BOM + RFC 4180 quoting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(_UTF8_BOM)
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def export_csv_bollette(
    con: sqlite3.Connection,
    output_path: Path,
    anno: int | None = None,
    utenza_id: int | None = None,
) -> int:
    """Export bollette + utenza JOIN. Returns numero righe esportate."""
    where_clauses: list[str] = []
    params: list = []
    if anno is not None:
        where_clauses.append("b.periodo_inizio LIKE ?")
        params.append(f"{anno}-%")
    if utenza_id is not None:
        where_clauses.append("b.utenza_id = ?")
        params.append(utenza_id)
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = (
        "SELECT u.alias, u.tipo, u.fornitore, u.pod_pdr, "  # nosec B608 - where_sql composto da clausole hardcoded con placeholder ?, params parametrizzati via con.execute(query, params)
        "b.periodo_inizio, b.periodo_fine, b.consumo_qta, b.consumo_unita, "
        "b.importo_totale, b.iva, b.scadenza, b.parser_usato, b.confidence, "
        "b.imported_at "
        "FROM bollette b JOIN utenze u ON u.id = b.utenza_id"
        + where_sql
        + " ORDER BY b.periodo_inizio DESC, u.alias"
    )
    cur = con.execute(query, params)
    headers = [
        "utenza",
        "tipo",
        "fornitore",
        "pod_pdr",
        "periodo_inizio",
        "periodo_fine",
        "consumo_qta",
        "consumo_unita",
        "importo_totale_eur",
        "iva_eur",
        "scadenza",
        "parser_usato",
        "confidence",
        "imported_at",
    ]
    rows = [list(row) for row in cur.fetchall()]
    _write_csv(output_path, headers, rows)
    return len(rows)


def export_csv_alerts(
    con: sqlite3.Connection,
    output_path: Path,
    include_dismissed: bool = False,
) -> int:
    """Export alert storico. Returns numero righe."""
    query = (
        "SELECT a.id, a.tipo, u.alias AS utenza_alias, a.bolletta_id, "
        "a.messaggio, a.created_at, a.dismissed_at "
        "FROM alert a LEFT JOIN utenze u ON u.id = a.utenza_id"
    )
    if not include_dismissed:
        query += " WHERE a.dismissed_at IS NULL"
    query += " ORDER BY a.created_at DESC"

    cur = con.execute(query)
    headers = [
        "alert_id",
        "tipo",
        "utenza",
        "bolletta_id",
        "messaggio",
        "created_at",
        "dismissed_at",
    ]
    rows = [list(row) for row in cur.fetchall()]
    _write_csv(output_path, headers, rows)
    return len(rows)


def export_csv_deducibili(
    con: sqlite3.Connection,
    output_path: Path,
    anno: int,
    quota_studio_perc: float = 0.0,
) -> int:
    """Export utenze deducibili pro-quota studio (regime forfettario/ordinario).

    Args:
        anno: anno fiscale.
        quota_studio_perc: 0.0-1.0 (es. 0.30 = 30% utenza studio promiscua).
                          Applica moltiplicatore a importo_totale.
    """
    if not 0.0 <= quota_studio_perc <= 1.0:
        raise ValueError(
            f"quota_studio_perc deve essere 0.0-1.0, got {quota_studio_perc}"
        )

    query = (
        "SELECT u.id, u.alias, u.tipo, u.fornitore, u.pod_pdr, "
        "COUNT(b.id) AS num_bollette, "
        "SUM(b.importo_totale) AS totale_anno, "
        "SUM(b.iva) AS iva_anno "
        "FROM utenze u "
        "LEFT JOIN bollette b ON b.utenza_id = u.id "
        "AND b.periodo_inizio LIKE ? "
        "GROUP BY u.id "
        "HAVING num_bollette > 0 "
        "ORDER BY u.alias"
    )
    cur = con.execute(query, (f"{anno}-%",))
    headers = [
        "utenza_id",
        "alias",
        "tipo",
        "fornitore",
        "pod_pdr",
        "num_bollette",
        "totale_anno_eur",
        "iva_anno_eur",
        "quota_studio_perc",
        "deducibile_eur",
        "anno_fiscale",
    ]
    rows: list[list] = []
    for row in cur.fetchall():
        totale = row[6] or 0.0
        deducibile = round(totale * quota_studio_perc, 2)
        rows.append(
            [
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                round(totale, 2),
                round(row[7] or 0.0, 2),
                quota_studio_perc,
                deducibile,
                anno,
            ]
        )
    _write_csv(output_path, headers, rows)
    return len(rows)


def generate_filename(prefix: str, anno: int | None = None) -> str:
    """Helper: genera nome file CSV con timestamp ISO.

    Example: 'bollette_2026_export-2026-05-28.csv'
    """
    today_iso = date.today().isoformat()
    if anno is not None:
        return f"{prefix}_{anno}_export-{today_iso}.csv"
    return f"{prefix}_export-{today_iso}.csv"
