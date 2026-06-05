"""Services letture-contatori (utenze + letture + finestre autolettura)."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path


def init_db(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))


# --- Utenze ---


_TIPI_VALIDI = ("gas", "luce", "acqua")
_UM_DEFAULT = {"gas": "Smc", "luce": "kWh", "acqua": "mc"}


def add_utenza(conn: sqlite3.Connection, dati: dict) -> int:
    tipo = dati.get("tipo")
    if tipo not in _TIPI_VALIDI:
        raise ValueError(f"tipo deve essere uno di {_TIPI_VALIDI}")
    um = dati.get("unita_misura") or _UM_DEFAULT[tipo]
    cur = conn.execute(
        "INSERT INTO utenze (tipo, codice_pod_pdr, fornitore_attuale, distributore, "
        "unita_misura, tariffa_riferimento, fasce_orarie_attive, alias_utente) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tipo, dati.get("codice_pod_pdr"), dati.get("fornitore_attuale"),
         dati.get("distributore"), um, dati.get("tariffa_riferimento"),
         1 if dati.get("fasce_orarie_attive") else 0, dati.get("alias_utente")),
    )
    conn.commit()
    return cur.lastrowid


def list_utenze(conn: sqlite3.Connection, tipo: str | None = None) -> list[dict]:
    if tipo:
        rows = conn.execute(
            "SELECT * FROM utenze WHERE tipo=? ORDER BY alias_utente, id",
            (tipo,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM utenze ORDER BY tipo, alias_utente, id").fetchall()
    return [dict(r) for r in rows]


def get_utenza(conn: sqlite3.Connection, uid: int) -> dict | None:
    row = conn.execute("SELECT * FROM utenze WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


def delete_utenza(conn: sqlite3.Connection, uid: int) -> None:
    conn.execute("DELETE FROM utenze WHERE id=?", (uid,))
    conn.commit()


# --- Letture ---


_TIPI_LETTURA = ("autolettura", "stimata", "effettiva-distributore", "controllo")


def add_lettura(conn: sqlite3.Connection, dati: dict) -> int:
    if not dati.get("utenza_id"):
        raise ValueError("utenza_id obbligatorio")
    if dati.get("valore") is None:
        raise ValueError("valore obbligatorio")
    if float(dati["valore"]) < 0:
        raise ValueError("valore non può essere negativo")
    tipo_lettura = dati.get("tipo_lettura", "autolettura")
    if tipo_lettura not in _TIPI_LETTURA:
        raise ValueError(f"tipo_lettura deve essere uno di {_TIPI_LETTURA}")
    cur = conn.execute(
        "INSERT INTO letture (utenza_id, data_lettura, valore, valore_f1, "
        "valore_f2, valore_f3, tipo_lettura, foto_path, comunicata_al_fornitore, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dati["utenza_id"],
            dati.get("data_lettura", date.today().isoformat()),
            float(dati["valore"]),
            dati.get("valore_f1"), dati.get("valore_f2"), dati.get("valore_f3"),
            tipo_lettura, dati.get("foto_path"),
            1 if dati.get("comunicata_al_fornitore") else 0,
            dati.get("note"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_letture(conn: sqlite3.Connection, utenza_id: int | None = None,
                 limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM letture"
    params: list = []
    if utenza_id:
        sql += " WHERE utenza_id=?"
        params.append(utenza_id)
    sql += " ORDER BY data_lettura DESC, id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def ultima_lettura(conn: sqlite3.Connection, utenza_id: int) -> dict | None:
    rows = list_letture(conn, utenza_id, limit=1)
    return rows[0] if rows else None


def consumo_periodo(conn: sqlite3.Connection, utenza_id: int,
                    data_inizio: str, data_fine: str) -> dict:
    rows = conn.execute(
        "SELECT * FROM letture WHERE utenza_id=? AND data_lettura BETWEEN ? AND ? "
        "ORDER BY data_lettura",
        (utenza_id, data_inizio, data_fine),
    ).fetchall()
    if len(rows) < 2:
        return {"consumo": None, "n_letture": len(rows),
                "lettura_iniziale": dict(rows[0]) if rows else None,
                "lettura_finale": None}
    primo, ultimo = dict(rows[0]), dict(rows[-1])
    consumo = ultimo["valore"] - primo["valore"]
    giorni = _giorni_tra(primo["data_lettura"], ultimo["data_lettura"])
    return {
        "consumo": consumo,
        "n_letture": len(rows),
        "lettura_iniziale": primo,
        "lettura_finale": ultimo,
        "giorni": giorni,
        "consumo_giornaliero_medio": consumo / max(1, giorni),
    }


def _giorni_tra(d1_iso: str, d2_iso: str) -> int:
    d1 = date.fromisoformat(d1_iso)
    d2 = date.fromisoformat(d2_iso)
    return (d2 - d1).days


# --- Finestre autolettura ---


def add_finestra(conn: sqlite3.Connection, utenza_id: int, mese_anno: str,
                 giorno_inizio: int, giorno_fine: int) -> int:
    if not 1 <= giorno_inizio <= 31:
        raise ValueError("giorno_inizio deve essere tra 1 e 31")
    if not 1 <= giorno_fine <= 31:
        raise ValueError("giorno_fine deve essere tra 1 e 31")
    if giorno_fine < giorno_inizio:
        raise ValueError("giorno_fine deve essere >= giorno_inizio")
    cur = conn.execute(
        "INSERT INTO finestre_autolettura (utenza_id, mese_anno, giorno_inizio, giorno_fine) "
        "VALUES (?, ?, ?, ?)",
        (utenza_id, mese_anno, giorno_inizio, giorno_fine),
    )
    conn.commit()
    return cur.lastrowid


def finestre_aperte(conn: sqlite3.Connection, oggi: date | None = None) -> list[dict]:
    if oggi is None:
        oggi = date.today()
    rows = conn.execute(
        "SELECT f.*, u.alias_utente, u.tipo FROM finestre_autolettura f "
        "JOIN utenze u ON u.id = f.utenza_id "
        "WHERE f.finestra_chiusa=0 AND f.mese_anno=? "
        "AND ? BETWEEN f.giorno_inizio AND f.giorno_fine",
        (oggi.strftime("%Y-%m"), oggi.day),
    ).fetchall()
    return [dict(r) for r in rows]


def chiudi_finestra(conn: sqlite3.Connection, fid: int) -> None:
    conn.execute("UPDATE finestre_autolettura SET finestra_chiusa=1 WHERE id=?", (fid,))
    conn.commit()


# --- Dashboard ---


def riepilogo_dashboard(conn: sqlite3.Connection) -> dict:
    n_utenze = conn.execute("SELECT COUNT(*) FROM utenze").fetchone()[0]
    n_letture_anno = conn.execute(
        "SELECT COUNT(*) FROM letture WHERE data_lettura >= date('now','-365 days')"
    ).fetchone()[0]
    n_finestre = len(finestre_aperte(conn))
    return {
        "n_utenze": n_utenze,
        "n_letture_ultimo_anno": n_letture_anno,
        "n_finestre_aperte_oggi": n_finestre,
    }
