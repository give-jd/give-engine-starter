"""Persistenza multi-CV su sqlite locale + export/import JSON (schema v1, compatibile col prototipo)."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def defaults() -> dict:
    return {
        "schema": 1, "lang": "it", "layout": "europass", "accent": "#1a5fb4",
        "personal": {"nome": "", "cognome": "", "email": "", "tel": "", "indirizzo": "",
                     "dataNascita": "", "nazionalita": "", "linkedin": "", "sito": "", "foto": None},
        "profilo": "",
        "esperienze": [], "istruzione": [],
        "competenze": {"lingue": [], "digitali": [], "soft": [], "patente": ""},
        "extra": {"certificazioni": [], "pubblicazioni": [], "note": ""},
        "privacy": {"tipo": "standard-it", "testoCustom": "", "dataFirma": False},
    }


def _pick(target: dict, src: dict) -> None:
    """Tiene solo le chiavi previste dallo schema; default sui buchi (porting di migrate() del prototipo)."""
    for k in list(target.keys()):
        if k not in src:
            continue
        if isinstance(target[k], dict) and isinstance(src[k], dict):
            _pick(target[k], src[k])
        else:
            target[k] = src[k]


def migrate(data: dict) -> dict:
    d = defaults()
    _pick(d, data or {})
    d["schema"] = 1
    return d


def export_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def import_json(text: str) -> dict:
    data = json.loads(text)          # json.JSONDecodeError è un ValueError
    if not isinstance(data, dict):
        raise ValueError("JSON non valido: atteso un oggetto")
    return migrate(data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(path: str | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("CURRICULUM_DB", "data/curriculum.db")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    con.commit()
    return con


def list_cvs(con: sqlite3.Connection) -> list[tuple[int, str, str]]:
    return list(con.execute("SELECT id, nome_cv, updated_at FROM cv ORDER BY updated_at DESC"))


def load_cv(con: sqlite3.Connection, cv_id: int) -> dict:
    row = con.execute("SELECT payload FROM cv WHERE id = ?", (cv_id,)).fetchone()
    if row is None:
        raise KeyError(f"CV {cv_id} inesistente")
    return migrate(json.loads(row[0]))


def save_cv(con: sqlite3.Connection, cv_id: int | None, nome_cv: str, data: dict) -> int:
    payload, now = export_json(data), _now()
    if cv_id is None:
        cur = con.execute("INSERT INTO cv (nome_cv, payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
                          (nome_cv, payload, now, now))
        con.commit()
        return cur.lastrowid
    con.execute("UPDATE cv SET nome_cv = ?, payload = ?, updated_at = ? WHERE id = ?",
                (nome_cv, payload, now, cv_id))
    con.commit()
    return cv_id


def delete_cv(con: sqlite3.Connection, cv_id: int) -> None:
    con.execute("DELETE FROM cv WHERE id = ?", (cv_id,))
    con.commit()
