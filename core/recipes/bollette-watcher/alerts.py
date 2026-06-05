"""Alerts engine: regole anomalia consumi/costo + scadenze imminenti.

Categorie alert (vedi schema.sql tabella `alert.tipo` CHECK):
- 'anomalia-consumi': consumo > ±soglia% vs media storica utenza
- 'anomalia-costo': importo_totale > ±soglia% vs media storica utenza
- 'scadenza': bolletta in scadenza < N giorni

Default soglie:
- soglia_anomalia_perc: float 0.0-1.0 (default 0.25 = ±25%)
- giorni_scadenza_alert: int (default 7)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta


DEFAULT_SOGLIA_ANOMALIA: float = 0.25  # ±25%
DEFAULT_GIORNI_SCADENZA: int = 7
MIN_STORICO_BOLLETTE: int = 3  # min N bollette per anomalia computation


@dataclass(frozen=True)
class AlertEvent:
    """Alert generato (non ancora persistito in DB)."""

    tipo: str  # 'anomalia-consumi' | 'anomalia-costo' | 'scadenza'
    utenza_id: int
    bolletta_id: int | None
    messaggio: str


def compute_anomalia_consumi(
    con: sqlite3.Connection,
    utenza_id: int,
    nuova_bolletta_id: int,
    soglia_perc: float = DEFAULT_SOGLIA_ANOMALIA,
) -> AlertEvent | None:
    """Verifica se nuova bolletta ha consumo > ±soglia% vs media storica."""
    cur = con.execute(
        "SELECT consumo_qta FROM bollette "
        "WHERE utenza_id = ? AND id != ? AND consumo_qta IS NOT NULL "
        "ORDER BY periodo_inizio DESC LIMIT 12",
        (utenza_id, nuova_bolletta_id),
    )
    storico = [row[0] for row in cur.fetchall() if row[0] is not None]
    if len(storico) < MIN_STORICO_BOLLETTE:
        return None

    nuova_row = con.execute(
        "SELECT consumo_qta FROM bollette WHERE id = ?", (nuova_bolletta_id,)
    ).fetchone()
    if nuova_row is None or nuova_row[0] is None:
        return None

    nuova_qta = float(nuova_row[0])
    if nuova_qta <= 0:
        return None
    media = sum(storico) / len(storico)
    if media <= 0:
        return None
    delta_perc = (nuova_qta - media) / media

    if abs(delta_perc) >= soglia_perc:
        sign = "+" if delta_perc > 0 else "-"
        return AlertEvent(
            tipo="anomalia-consumi",
            utenza_id=utenza_id,
            bolletta_id=nuova_bolletta_id,
            messaggio=(
                f"Consumo bolletta {sign}{abs(delta_perc) * 100:.1f}% "
                f"vs media storica ({media:.1f})"
            ),
        )
    return None


def compute_anomalia_costo(
    con: sqlite3.Connection,
    utenza_id: int,
    nuova_bolletta_id: int,
    soglia_perc: float = DEFAULT_SOGLIA_ANOMALIA,
) -> AlertEvent | None:
    """Verifica se nuova bolletta ha importo > ±soglia% vs media storica."""
    cur = con.execute(
        "SELECT importo_totale FROM bollette "
        "WHERE utenza_id = ? AND id != ? AND importo_totale IS NOT NULL "
        "ORDER BY periodo_inizio DESC LIMIT 12",
        (utenza_id, nuova_bolletta_id),
    )
    storico = [row[0] for row in cur.fetchall() if row[0] is not None]
    if len(storico) < MIN_STORICO_BOLLETTE:
        return None

    nuova_row = con.execute(
        "SELECT importo_totale FROM bollette WHERE id = ?", (nuova_bolletta_id,)
    ).fetchone()
    if nuova_row is None or nuova_row[0] is None:
        return None

    nuova_imp = float(nuova_row[0])
    media = sum(storico) / len(storico)
    if media <= 0:
        return None
    delta_perc = (nuova_imp - media) / media

    if abs(delta_perc) >= soglia_perc:
        sign = "+" if delta_perc > 0 else "-"
        return AlertEvent(
            tipo="anomalia-costo",
            utenza_id=utenza_id,
            bolletta_id=nuova_bolletta_id,
            messaggio=(
                f"Importo bolletta {sign}{abs(delta_perc) * 100:.1f}% "
                f"vs media storica (€{media:.2f})"
            ),
        )
    return None


def compute_scadenze_imminenti(
    con: sqlite3.Connection,
    today: date | None = None,
    giorni_anticipo: int = DEFAULT_GIORNI_SCADENZA,
) -> list[AlertEvent]:
    """Trova bollette con scadenza < N giorni da oggi (no alert attivo)."""
    today = today or date.today()
    limite = today + timedelta(days=giorni_anticipo)
    cur = con.execute(
        "SELECT b.id, b.utenza_id, b.scadenza "
        "FROM bollette b "
        "LEFT JOIN alert a ON a.bolletta_id = b.id "
        "  AND a.tipo = 'scadenza' AND a.dismissed_at IS NULL "
        "WHERE b.scadenza IS NOT NULL "
        "AND a.id IS NULL "
        "AND DATE(b.scadenza) BETWEEN ? AND ?",
        (today.isoformat(), limite.isoformat()),
    )
    out: list[AlertEvent] = []
    for row in cur.fetchall():
        bid, uid, scad = row
        try:
            scad_date = datetime.strptime(scad, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        giorni_residui = (scad_date - today).days
        out.append(
            AlertEvent(
                tipo="scadenza",
                utenza_id=uid,
                bolletta_id=bid,
                messaggio=f"Bolletta in scadenza fra {giorni_residui} giorni ({scad})",
            )
        )
    return out


def persist_alert(con: sqlite3.Connection, event: AlertEvent) -> int:
    """Inserisci alert in DB. Returns alert id."""
    cur = con.execute(
        "INSERT INTO alert(utenza_id, bolletta_id, tipo, messaggio) VALUES(?, ?, ?, ?)",
        (event.utenza_id, event.bolletta_id, event.tipo, event.messaggio),
    )
    con.commit()
    return cur.lastrowid


def run_post_import_checks(
    con: sqlite3.Connection,
    utenza_id: int,
    nuova_bolletta_id: int,
    soglia_perc: float = DEFAULT_SOGLIA_ANOMALIA,
) -> list[int]:
    """Post-import alert orchestrator. Returns list[alert_id] inseriti."""
    alert_ids: list[int] = []
    for fn in (compute_anomalia_consumi, compute_anomalia_costo):
        ev = fn(con, utenza_id, nuova_bolletta_id, soglia_perc=soglia_perc)
        if ev is not None:
            alert_ids.append(persist_alert(con, ev))
    return alert_ids


def run_periodic_scadenze(
    con: sqlite3.Connection,
    today: date | None = None,
    giorni_anticipo: int = DEFAULT_GIORNI_SCADENZA,
) -> list[int]:
    """Scheduled scadenze check (called daily). Returns alert ids inseriti."""
    events = compute_scadenze_imminenti(con, today, giorni_anticipo)
    return [persist_alert(con, ev) for ev in events]


def list_active(con: sqlite3.Connection) -> list[dict]:
    """Lista alert attivi (non dismissed)."""
    cur = con.execute(
        "SELECT id, utenza_id, bolletta_id, tipo, messaggio, created_at "
        "FROM alert WHERE dismissed_at IS NULL ORDER BY created_at DESC"
    )
    return [
        {
            "id": r[0],
            "utenza_id": r[1],
            "bolletta_id": r[2],
            "tipo": r[3],
            "messaggio": r[4],
            "created_at": r[5],
        }
        for r in cur.fetchall()
    ]


def dismiss(con: sqlite3.Connection, alert_id: int) -> None:
    """Marca alert come dismissed."""
    con.execute(
        "UPDATE alert SET dismissed_at = datetime('now') WHERE id = ?",
        (alert_id,),
    )
    con.commit()
