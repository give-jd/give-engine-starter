"""Services scadenze-auto-casa (scadenze + pagamenti storici + ricorrenze)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path


def init_db(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))


_CATEGORIE = ("auto", "casa", "persona")
_FREQUENZE = ("mensile", "bimestrale", "trimestrale", "quadrimestrale",
              "semestrale", "annuale", "biennale", "una-tantum", "custom")


# --- Scadenze CRUD ---


def add_scadenza(conn: sqlite3.Connection, dati: dict) -> int:
    if dati.get("categoria") not in _CATEGORIE:
        raise ValueError(f"categoria deve essere uno di {_CATEGORIE}")
    if not dati.get("tipo"):
        raise ValueError("tipo obbligatorio")
    if not dati.get("prossima_scadenza"):
        raise ValueError("prossima_scadenza obbligatoria")
    freq = dati.get("frequenza_tipo", "annuale")
    if freq not in _FREQUENZE:
        raise ValueError(f"frequenza_tipo deve essere uno di {_FREQUENZE}")
    if freq == "custom" and not dati.get("frequenza_custom_giorni"):
        raise ValueError("frequenza_custom_giorni obbligatoria per frequenza custom")
    cur = conn.execute(
        "INSERT INTO scadenze (categoria, tipo, oggetto, prossima_scadenza, "
        "frequenza_tipo, frequenza_custom_giorni, importo_previsto_eur, note, "
        "notifiche_attive, giorni_anticipo_notifica) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dati["categoria"], dati["tipo"], dati.get("oggetto"),
            dati["prossima_scadenza"], freq, dati.get("frequenza_custom_giorni"),
            dati.get("importo_previsto_eur"), dati.get("note"),
            1 if dati.get("notifiche_attive", True) else 0,
            int(dati.get("giorni_anticipo_notifica", 14)),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_scadenza(conn: sqlite3.Connection, sid: int) -> dict | None:
    row = conn.execute("SELECT * FROM scadenze WHERE id=?", (sid,)).fetchone()
    return dict(row) if row else None


def list_scadenze(conn: sqlite3.Connection, categoria: str | None = None) -> list[dict]:
    if categoria:
        if categoria not in _CATEGORIE:
            raise ValueError(f"categoria deve essere uno di {_CATEGORIE}")
        rows = conn.execute(
            "SELECT * FROM scadenze WHERE categoria=? ORDER BY prossima_scadenza",
            (categoria,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM scadenze ORDER BY prossima_scadenza"
        ).fetchall()
    return [dict(r) for r in rows]


def update_scadenza(conn: sqlite3.Connection, sid: int, updates: dict) -> None:
    if not get_scadenza(conn, sid):
        raise ValueError(f"scadenza {sid} non trovata")
    keys = ", ".join(f"{k}=?" for k in updates)
    conn.execute(
        f"UPDATE scadenze SET {keys}, updated_at=CURRENT_TIMESTAMP WHERE id=?",  # nosec B608 - keys da dict controllato
        list(updates.values()) + [sid],
    )
    conn.commit()


def delete_scadenza(conn: sqlite3.Connection, sid: int) -> None:
    conn.execute("DELETE FROM scadenze WHERE id=?", (sid,))
    conn.commit()


# --- Pagamenti storici ---


def registra_pagamento(conn: sqlite3.Connection, sid: int, dati: dict) -> int:
    if not dati.get("data_pagamento"):
        raise ValueError("data_pagamento obbligatoria")
    scad = get_scadenza(conn, sid)
    if not scad:
        raise ValueError(f"scadenza {sid} non trovata")
    cur = conn.execute(
        "INSERT INTO pagamenti_storici (scadenza_id, data_pagamento, "
        "importo_pagato_eur, metodo, riferimento, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            sid, dati["data_pagamento"], dati.get("importo_pagato_eur"),
            dati.get("metodo"), dati.get("riferimento"), dati.get("note"),
        ),
    )
    nuova = prossima_scadenza_da_ricorrenza(
        date.fromisoformat(dati["data_pagamento"]),
        scad["frequenza_tipo"],
        scad.get("frequenza_custom_giorni"),
    )
    if nuova:
        conn.execute(
            "UPDATE scadenze SET prossima_scadenza=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (nuova.isoformat(), sid),
        )
    conn.commit()
    return cur.lastrowid


def storico_pagamenti(conn: sqlite3.Connection, sid: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM pagamenti_storici WHERE scadenza_id=? "
        "ORDER BY data_pagamento DESC",
        (sid,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Ricorrenze ---


def prossima_scadenza_da_ricorrenza(da_data: date, frequenza: str,
                                    custom_giorni: int | None = None) -> date | None:
    if frequenza == "una-tantum":
        return None
    days_map = {
        "mensile": 30, "bimestrale": 60, "trimestrale": 91,
        "quadrimestrale": 122, "semestrale": 182, "annuale": 365,
        "biennale": 730,
    }
    if frequenza == "custom":
        if not custom_giorni:
            raise ValueError("custom_giorni richiesto per frequenza custom")
        return da_data + timedelta(days=int(custom_giorni))
    if frequenza in days_map:
        return da_data + timedelta(days=days_map[frequenza])
    raise ValueError(f"frequenza non riconosciuta: {frequenza}")


# --- Notifiche / alert ---


def scadenze_in_arrivo(conn: sqlite3.Connection,
                      oggi: date | None = None) -> list[dict]:
    if oggi is None:
        oggi = date.today()
    rows = conn.execute(
        "SELECT * FROM scadenze WHERE notifiche_attive=1 "
        "AND date(prossima_scadenza) <= date(?, '+' || giorni_anticipo_notifica || ' days') "
        "AND date(prossima_scadenza) >= date(?) "
        "ORDER BY prossima_scadenza",
        (oggi.isoformat(), oggi.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def scadenze_scadute(conn: sqlite3.Connection,
                    oggi: date | None = None) -> list[dict]:
    if oggi is None:
        oggi = date.today()
    rows = conn.execute(
        "SELECT * FROM scadenze WHERE date(prossima_scadenza) < date(?) "
        "ORDER BY prossima_scadenza",
        (oggi.isoformat(),),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Dashboard ---


def riepilogo_dashboard(conn: sqlite3.Connection) -> dict:
    n_totali = conn.execute("SELECT COUNT(*) FROM scadenze").fetchone()[0]
    per_categoria = {}
    for cat in _CATEGORIE:
        per_categoria[cat] = conn.execute(
            "SELECT COUNT(*) FROM scadenze WHERE categoria=?", (cat,)
        ).fetchone()[0]
    n_in_arrivo = len(scadenze_in_arrivo(conn))
    n_scadute = len(scadenze_scadute(conn))
    spesa_annuale_prevista = conn.execute(
        "SELECT COALESCE(SUM(importo_previsto_eur), 0) FROM scadenze "
        "WHERE importo_previsto_eur IS NOT NULL"
    ).fetchone()[0]
    return {
        "n_scadenze_totali": n_totali,
        "per_categoria": per_categoria,
        "n_in_arrivo": n_in_arrivo,
        "n_scadute": n_scadute,
        "spesa_annuale_prevista_eur": spesa_annuale_prevista,
    }
