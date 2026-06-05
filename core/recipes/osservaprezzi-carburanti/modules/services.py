"""Services osservaprezzi-carburanti (distributori + prezzi + preferiti + rifornimenti)."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path


def init_db(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))


# --- Distributori ---


def upsert_distributore(conn: sqlite3.Connection, dati: dict) -> None:
    if not dati.get("id"):
        raise ValueError("id obbligatorio (MIMIT impianto_id)")
    conn.execute(
        "INSERT OR REPLACE INTO distributori (id, bandiera, tipo_impianto, "
        "nome_impianto, indirizzo, comune, provincia, latitudine, longitudine, "
        "ultimo_aggiornamento_anagrafica) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dati["id"], dati.get("bandiera"), dati.get("tipo_impianto"),
            dati.get("nome_impianto"), dati.get("indirizzo"), dati.get("comune"),
            dati.get("provincia"), dati.get("latitudine"), dati.get("longitudine"),
            dati.get("ultimo_aggiornamento_anagrafica", date.today().isoformat()),
        ),
    )
    conn.commit()


def get_distributore(conn: sqlite3.Connection, did: int) -> dict | None:
    row = conn.execute("SELECT * FROM distributori WHERE id=?", (did,)).fetchone()
    return dict(row) if row else None


def search_distributori(conn: sqlite3.Connection, comune: str,
                       carburante: str = "Benzina") -> list[dict]:
    rows = conn.execute(
        """SELECT d.*, p.prezzo_self, p.prezzo_servito, p.data_comunicazione
        FROM distributori d
        LEFT JOIN prezzi p ON p.distributore_id = d.id AND p.carburante = ?
        AND p.id = (
            SELECT id FROM prezzi
            WHERE distributore_id = d.id AND carburante = ?
            ORDER BY data_comunicazione DESC LIMIT 1
        )
        WHERE d.comune LIKE ?
        ORDER BY p.prezzo_self IS NULL, p.prezzo_self""",
        (carburante, carburante, f"%{comune}%"),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Prezzi ---


_CARBURANTI = ("Benzina", "Diesel", "GPL", "Metano", "HVO")


def aggiorna_prezzo(conn: sqlite3.Connection, distributore_id: int, dati: dict) -> int:
    if dati.get("carburante") not in _CARBURANTI:
        raise ValueError(f"carburante deve essere uno di {_CARBURANTI}")
    if not dati.get("data_comunicazione"):
        raise ValueError("data_comunicazione obbligatoria")
    self_p = dati.get("prezzo_self")
    serv_p = dati.get("prezzo_servito")
    if self_p is None and serv_p is None:
        raise ValueError("almeno uno tra prezzo_self e prezzo_servito obbligatorio")
    for p in (self_p, serv_p):
        if p is not None and float(p) <= 0:
            raise ValueError("prezzo deve essere positivo")
    cur = conn.execute(
        "INSERT OR REPLACE INTO prezzi (distributore_id, carburante, "
        "prezzo_self, prezzo_servito, data_comunicazione) "
        "VALUES (?, ?, ?, ?, ?)",
        (distributore_id, dati["carburante"], self_p, serv_p, dati["data_comunicazione"]),
    )
    conn.commit()
    return cur.lastrowid


def ultimo_prezzo(conn: sqlite3.Connection, distributore_id: int,
                  carburante: str = "Benzina") -> dict | None:
    row = conn.execute(
        "SELECT * FROM prezzi WHERE distributore_id=? AND carburante=? "
        "ORDER BY data_comunicazione DESC LIMIT 1",
        (distributore_id, carburante),
    ).fetchone()
    return dict(row) if row else None


# --- Preferiti ---


def add_preferito(conn: sqlite3.Connection, distributore_id: int,
                  etichetta: str | None = None,
                  alert_sotto_eur: float | None = None,
                  carburante_principale: str = "Benzina") -> int:
    if not get_distributore(conn, distributore_id):
        raise ValueError(f"distributore {distributore_id} non esiste")
    if carburante_principale not in _CARBURANTI:
        raise ValueError(f"carburante deve essere uno di {_CARBURANTI}")
    cur = conn.execute(
        "INSERT INTO preferiti (distributore_id, etichetta_utente, "
        "alert_sotto_eur, carburante_principale) VALUES (?, ?, ?, ?)",
        (distributore_id, etichetta, alert_sotto_eur, carburante_principale),
    )
    conn.commit()
    return cur.lastrowid


def list_preferiti(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT pr.*, d.bandiera, d.nome_impianto, d.comune, d.provincia,
        p.prezzo_self, p.data_comunicazione
        FROM preferiti pr
        JOIN distributori d ON d.id = pr.distributore_id
        LEFT JOIN prezzi p ON p.distributore_id = d.id AND p.carburante = pr.carburante_principale
        AND p.id = (
            SELECT id FROM prezzi
            WHERE distributore_id = d.id AND carburante = pr.carburante_principale
            ORDER BY data_comunicazione DESC LIMIT 1
        )
        ORDER BY pr.ordine, pr.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def preferiti_in_alert(conn: sqlite3.Connection) -> list[dict]:
    preferiti = list_preferiti(conn)
    return [p for p in preferiti
            if p.get("alert_sotto_eur") is not None
            and p.get("prezzo_self") is not None
            and p["prezzo_self"] <= p["alert_sotto_eur"]]


def rimuovi_preferito(conn: sqlite3.Connection, preferito_id: int) -> None:
    conn.execute("DELETE FROM preferiti WHERE id=?", (preferito_id,))
    conn.commit()


# --- Rifornimenti personali ---


def add_rifornimento(conn: sqlite3.Connection, dati: dict) -> int:
    if not dati.get("data"):
        raise ValueError("data obbligatoria")
    if dati.get("carburante") not in _CARBURANTI:
        raise ValueError(f"carburante deve essere uno di {_CARBURANTI}")
    if not dati.get("litri") or float(dati["litri"]) <= 0:
        raise ValueError("litri deve essere positivo")
    if not dati.get("prezzo_unitario") or float(dati["prezzo_unitario"]) <= 0:
        raise ValueError("prezzo_unitario deve essere positivo")
    prezzo_tot = float(dati["litri"]) * float(dati["prezzo_unitario"])
    cur = conn.execute(
        "INSERT INTO rifornimenti (distributore_id, data, carburante, litri, "
        "prezzo_unitario, prezzo_totale, km_attuali, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dati.get("distributore_id"), dati["data"], dati["carburante"],
            float(dati["litri"]), float(dati["prezzo_unitario"]),
            round(prezzo_tot, 2), dati.get("km_attuali"), dati.get("note"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_rifornimenti(conn: sqlite3.Connection,
                     anno: int | None = None) -> list[dict]:
    if anno:
        rows = conn.execute(
            "SELECT * FROM rifornimenti WHERE strftime('%Y', data) = ? "
            "ORDER BY data DESC",
            (str(anno),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM rifornimenti ORDER BY data DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def consumo_medio(conn: sqlite3.Connection,
                 anno: int | None = None) -> dict:
    rifornimenti = sorted(
        [r for r in list_rifornimenti(conn, anno) if r.get("km_attuali")],
        key=lambda r: r["km_attuali"],
    )
    if len(rifornimenti) < 2:
        return {"km_totali": 0, "litri_totali": 0,
                "consumo_l_per_100km": None, "n_rifornimenti": len(rifornimenti)}
    km_iniziali = rifornimenti[0]["km_attuali"]
    km_finali = rifornimenti[-1]["km_attuali"]
    km_totali = km_finali - km_iniziali
    litri_totali = sum(r["litri"] for r in rifornimenti[1:])
    if km_totali <= 0:
        return {"km_totali": km_totali, "litri_totali": litri_totali,
                "consumo_l_per_100km": None, "n_rifornimenti": len(rifornimenti)}
    return {
        "km_totali": km_totali,
        "litri_totali": round(litri_totali, 2),
        "consumo_l_per_100km": round(litri_totali / km_totali * 100, 2),
        "n_rifornimenti": len(rifornimenti),
    }


# --- Refresh MIMIT log ---


def log_refresh_mimit(conn: sqlite3.Connection, esito: str,
                     righe_anagrafica: int = 0, righe_prezzi: int = 0,
                     note: str | None = None) -> int:
    from datetime import datetime
    cur = conn.execute(
        "INSERT INTO refresh_mimit (data_refresh, esito, righe_anagrafica, "
        "righe_prezzi, note) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), esito, righe_anagrafica, righe_prezzi, note),
    )
    conn.commit()
    return cur.lastrowid


def ultimo_refresh(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM refresh_mimit ORDER BY data_refresh DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
