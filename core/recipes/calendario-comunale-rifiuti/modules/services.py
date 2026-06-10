"""Logica calendario-comunale-rifiuti: CRUD + motore ricorrenze + promemoria.

Modulo puro e testabile: nessuna dipendenza da Streamlit. Le date sono stringhe
ISO ``YYYY-MM-DD``; ``now`` per i promemoria e' un ``datetime`` locale.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

_TIPI_RICORRENZA = ("settimanale", "quindicinale", "mensile", "lista_date")


def init_db(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Inizializza lo schema sul connection passato.

    Args:
        conn: Connessione SQLite (in-memory o su file).
        schema_path: Path opzionale allo ``schema.sql``; default = quello della ricetta.
    """
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()


# --- Frazioni CRUD ---


def add_frazione(conn: sqlite3.Connection, dati: dict) -> int:
    """Crea una frazione. Richiede ``nome``.

    Args:
        conn: Connessione.
        dati: Dict con ``nome`` (obbligatorio), ``colore``, ``icona``, ``attiva``.

    Returns:
        L'id della frazione creata.

    Raises:
        ValueError: Se ``nome`` manca.
    """
    if not dati.get("nome"):
        raise ValueError("nome frazione obbligatorio")
    cur = conn.execute(
        "INSERT INTO frazioni (nome, colore, icona, attiva) VALUES (?, ?, ?, ?)",
        (
            dati["nome"], dati.get("colore"), dati.get("icona"),
            1 if dati.get("attiva", True) else 0,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_frazioni(conn: sqlite3.Connection, solo_attive: bool = False) -> list[dict]:
    """Elenca le frazioni, opzionalmente solo le attive."""
    sql = "SELECT * FROM frazioni"
    if solo_attive:
        sql += " WHERE attiva=1"
    sql += " ORDER BY nome"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def get_frazione(conn: sqlite3.Connection, fid: int) -> dict | None:
    """Restituisce la frazione per id, o ``None``."""
    row = conn.execute("SELECT * FROM frazioni WHERE id=?", (fid,)).fetchone()
    return dict(row) if row else None


def delete_frazione(conn: sqlite3.Connection, fid: int) -> None:
    """Elimina una frazione (CASCADE su ricorrenze/eccezioni/regolamento/promemoria)."""
    conn.execute("DELETE FROM frazioni WHERE id=?", (fid,))
    conn.commit()


# --- Ricorrenze CRUD + validazione ---


def _valida_ricorrenza(dati: dict) -> None:
    """Valida la coerenza di una ricorrenza. Solleva ValueError se incoerente."""
    tipo = dati.get("tipo")
    if tipo not in _TIPI_RICORRENZA:
        raise ValueError(f"tipo ricorrenza deve essere uno di {_TIPI_RICORRENZA}")
    if tipo in ("settimanale", "quindicinale"):
        giorni = (dati.get("giorni_settimana") or "").strip()
        if not giorni:
            raise ValueError(f"{tipo}: giorni_settimana obbligatorio (es. '1,4')")
        for g in giorni.split(","):
            if g.strip() and not (1 <= int(g) <= 7):
                raise ValueError("giorni_settimana: valori ISO 1..7 (1=lun, 7=dom)")
    if tipo == "quindicinale" and not dati.get("valido_da"):
        raise ValueError("quindicinale: valido_da (ancora di parita') obbligatorio")
    if tipo == "mensile" and not dati.get("giorno_mese"):
        raise ValueError("mensile: giorno_mese obbligatorio (1..31)")
    if tipo == "lista_date" and not (dati.get("date_extra") or "").strip():
        raise ValueError("lista_date: date_extra obbligatorio (CSV ISO)")


def add_ricorrenza(conn: sqlite3.Connection, dati: dict) -> int:
    """Crea una ricorrenza per una frazione, dopo validazione.

    Args:
        conn: Connessione.
        dati: Dict con ``frazione_id``, ``tipo`` e i campi specifici del tipo.

    Returns:
        L'id della ricorrenza creata.

    Raises:
        ValueError: Se la ricorrenza e' incoerente (vedi ``_valida_ricorrenza``).
    """
    if not dati.get("frazione_id"):
        raise ValueError("frazione_id obbligatorio")
    _valida_ricorrenza(dati)
    cur = conn.execute(
        "INSERT INTO ricorrenze (frazione_id, tipo, giorni_settimana, "
        "settimane_alterne, giorno_mese, date_extra, valido_da, valido_a, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dati["frazione_id"], dati["tipo"], dati.get("giorni_settimana"),
            1 if dati.get("settimane_alterne") else 0, dati.get("giorno_mese"),
            dati.get("date_extra"), dati.get("valido_da"), dati.get("valido_a"),
            dati.get("note"),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_ricorrenze(conn: sqlite3.Connection, frazione_id: int | None = None) -> list[dict]:
    """Elenca le ricorrenze, opzionalmente filtrate per frazione."""
    if frazione_id is not None:
        rows = conn.execute(
            "SELECT * FROM ricorrenze WHERE frazione_id=?", (frazione_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM ricorrenze").fetchall()
    return [dict(r) for r in rows]


def delete_ricorrenza(conn: sqlite3.Connection, rid: int) -> None:
    """Elimina una ricorrenza."""
    conn.execute("DELETE FROM ricorrenze WHERE id=?", (rid,))
    conn.commit()


# --- Eccezioni ---


def add_eccezione(conn: sqlite3.Connection, dati: dict) -> int:
    """Crea un'eccezione (salta o sposta) per una data.

    Args:
        conn: Connessione.
        dati: Dict con ``data`` (ISO), ``frazione_id`` opzionale, ``salta`` bool,
            ``sposta_a`` (ISO) opzionale, ``motivo``.

    Returns:
        L'id dell'eccezione.

    Raises:
        ValueError: Se ``data`` manca, o se non-salta senza ``sposta_a``.
    """
    if not dati.get("data"):
        raise ValueError("data eccezione obbligatoria")
    salta = bool(dati.get("salta"))
    if not salta and not dati.get("sposta_a"):
        raise ValueError("eccezione: serve 'salta' oppure 'sposta_a'")
    cur = conn.execute(
        "INSERT INTO eccezioni (data, frazione_id, salta, sposta_a, motivo) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            dati["data"], dati.get("frazione_id"), 1 if salta else 0,
            dati.get("sposta_a"), dati.get("motivo"),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_eccezioni(conn: sqlite3.Connection) -> list[dict]:
    """Elenca tutte le eccezioni."""
    return [dict(r) for r in conn.execute("SELECT * FROM eccezioni").fetchall()]


# --- Regolamento ---


def add_voce_regolamento(conn: sqlite3.Connection, dati: dict) -> int:
    """Aggiunge una voce 'dove butto X' (materiale -> frazione).

    Args:
        conn: Connessione.
        dati: Dict con ``materiale`` (obbligatorio), ``frazione_id``, ``note``.

    Returns:
        L'id della voce.

    Raises:
        ValueError: Se ``materiale`` manca.
    """
    if not dati.get("materiale"):
        raise ValueError("materiale obbligatorio")
    cur = conn.execute(
        "INSERT INTO regolamento (materiale, frazione_id, note) VALUES (?, ?, ?)",
        (dati["materiale"], dati.get("frazione_id"), dati.get("note")),
    )
    conn.commit()
    return int(cur.lastrowid)


def cerca_materiale(conn: sqlite3.Connection, q: str) -> list[dict]:
    """Cerca nel regolamento il materiale (LIKE su materiale + note).

    Args:
        conn: Connessione.
        q: Testo di ricerca.

    Returns:
        Lista di dict ``{id, materiale, frazione, note}`` ordinati per materiale;
        vuota se nessun match o query vuota.
    """
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q.lower()}%"
    rows = conn.execute(
        "SELECT r.id, r.materiale, r.note, f.nome AS frazione "
        "FROM regolamento r LEFT JOIN frazioni f ON f.id = r.frazione_id "
        "WHERE LOWER(r.materiale) LIKE ? OR LOWER(COALESCE(r.note, '')) LIKE ? "
        "ORDER BY r.materiale",
        (like, like),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Promemoria ---


def add_promemoria(conn: sqlite3.Connection, dati: dict) -> int:
    """Crea un promemoria per una frazione.

    Args:
        conn: Connessione.
        dati: Dict con ``frazione_id`` (obbligatorio), ``anticipo_ore`` (default 12),
            ``ora_invio`` opzionale, ``attivo`` (default True).

    Returns:
        L'id del promemoria.

    Raises:
        ValueError: Se ``frazione_id`` manca.
    """
    if not dati.get("frazione_id"):
        raise ValueError("frazione_id obbligatorio")
    cur = conn.execute(
        "INSERT INTO promemoria (frazione_id, anticipo_ore, ora_invio, attivo) "
        "VALUES (?, ?, ?, ?)",
        (
            dati["frazione_id"], int(dati.get("anticipo_ore", 12)),
            dati.get("ora_invio"), 1 if dati.get("attivo", True) else 0,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_promemoria(conn: sqlite3.Connection) -> list[dict]:
    """Elenca tutti i promemoria con il nome della frazione."""
    rows = conn.execute(
        "SELECT p.*, f.nome AS frazione FROM promemoria p "
        "JOIN frazioni f ON f.id = p.frazione_id ORDER BY f.nome"
    ).fetchall()
    return [dict(r) for r in rows]


def marca_promemoria_inviato(conn: sqlite3.Connection, pid: int, giorno: date) -> None:
    """Marca un promemoria come inviato in ``giorno`` (dedup giornaliera)."""
    conn.execute(
        "UPDATE promemoria SET ultimo_inviato=? WHERE id=?",
        (giorno.isoformat(), pid),
    )
    conn.commit()


# --- Motore ricorrenze ---


def _parse_giorni(csv: str | None) -> list[int]:
    if not csv:
        return []
    return [int(g) for g in csv.split(",") if g.strip()]


def _espandi_ricorrenza(ric: dict, da: date, a: date) -> list[date]:
    """Espande una singola ricorrenza in date concrete nella finestra [da, a]."""
    tipo = ric["tipo"]
    valido_da = date.fromisoformat(ric["valido_da"]) if ric.get("valido_da") else None
    valido_a = date.fromisoformat(ric["valido_a"]) if ric.get("valido_a") else None

    def _in_validita(d: date) -> bool:
        if valido_da and d < valido_da:
            return False
        if valido_a and d > valido_a:
            return False
        return True

    out: list[date] = []

    if tipo == "lista_date":
        for s in (ric.get("date_extra") or "").split(","):
            s = s.strip()
            if not s:
                continue
            d = date.fromisoformat(s)
            if da <= d <= a and _in_validita(d):
                out.append(d)
        return out

    if tipo == "mensile":
        giorno = int(ric["giorno_mese"])
        cursor = da.replace(day=1)
        while cursor <= a:
            try:
                cand = cursor.replace(day=giorno)
            except ValueError:
                cand = None
            if cand is not None and da <= cand <= a and _in_validita(cand):
                out.append(cand)
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
        return sorted(set(out))

    # settimanale / quindicinale
    giorni = _parse_giorni(ric.get("giorni_settimana"))
    d = da
    while d <= a:
        if d.isoweekday() in giorni and _in_validita(d):
            if tipo == "settimanale":
                out.append(d)
            elif tipo == "quindicinale" and valido_da is not None:
                # parita': numero di settimane intere tra ancora e d deve essere pari.
                delta_giorni = (d - valido_da).days
                if delta_giorni >= 0 and (delta_giorni // 7) % 2 == 0:
                    out.append(d)
        d += timedelta(days=1)
    return out


def _applica_eccezioni(d: date, fid: int, eccezioni: list[dict]) -> date | None:
    """Applica le eccezioni a una data per una frazione.

    Un'eccezione si applica se la sua ``frazione_id`` e' NULL (vale per tutte)
    o coincide con ``fid``. ``salta`` -> None; ``sposta_a`` -> nuova data.
    """
    for ecc in eccezioni:
        if ecc["data"] != d.isoformat():
            continue
        if ecc["frazione_id"] is not None and ecc["frazione_id"] != fid:
            continue
        if ecc["salta"]:
            return None
        if ecc["sposta_a"]:
            return date.fromisoformat(ecc["sposta_a"])
    return d


def prossime_raccolte(
    conn: sqlite3.Connection, *, da: date, giorni: int
) -> list[dict]:
    """Espande tutte le ricorrenze (con eccezioni) in date concrete.

    Per ogni occorrenza applica le eccezioni: ``salta`` rimuove la data,
    ``sposta_a`` la rimpiazza con la nuova data (se ancora in finestra).

    Args:
        conn: Connessione.
        da: Data iniziale (inclusa).
        giorni: Ampiezza della finestra in giorni (``da`` + ``giorni`` inclusa).

    Returns:
        Lista di dict ``{data, frazione_id, frazione, colore, icona, tipo}``
        ordinata per data, poi per nome frazione.
    """
    a = da + timedelta(days=giorni)
    frazioni = {f["id"]: f for f in list_frazioni(conn, solo_attive=True)}
    eccezioni = list_eccezioni(conn)

    risultati: list[dict] = []
    for ric in list_ricorrenze(conn):
        fid = ric["frazione_id"]
        fr = frazioni.get(fid)
        if fr is None:
            continue  # frazione disattivata o assente
        for d in _espandi_ricorrenza(ric, da, a):
            d_eff = _applica_eccezioni(d, fid, eccezioni)
            if d_eff is None:
                continue
            if not (da <= d_eff <= a):
                continue
            risultati.append({
                "data": d_eff.isoformat(),
                "frazione_id": fid,
                "frazione": fr["nome"],
                "colore": fr.get("colore"),
                "icona": fr.get("icona"),
                "tipo": ric["tipo"],
            })

    # dedup (stessa frazione+data) e ordina
    visti: set[tuple[str, int]] = set()
    uniq: list[dict] = []
    for r in sorted(risultati, key=lambda x: (x["data"], x["frazione"])):
        key = (r["data"], r["frazione_id"])
        if key in visti:
            continue
        visti.add(key)
        uniq.append(r)
    return uniq


def promemoria_da_inviare(
    conn: sqlite3.Connection, *, now: datetime
) -> list[dict]:
    """Promemoria attivi con una raccolta entro ``anticipo_ore``, non gia' inviati oggi.

    Args:
        conn: Connessione.
        now: Momento corrente (datetime locale).

    Returns:
        Lista di dict ``{promemoria_id, frazione_id, frazione, data, anticipo_ore}``.
    """
    oggi = now.date()
    rows = conn.execute(
        "SELECT p.id AS promemoria_id, p.frazione_id, p.anticipo_ore, "
        "p.ultimo_inviato, f.nome AS frazione "
        "FROM promemoria p JOIN frazioni f ON f.id = p.frazione_id "
        "WHERE p.attivo=1"
    ).fetchall()
    if not rows:
        return []

    max_ore = max(int(r["anticipo_ore"]) for r in rows)
    orizzonte_giorni = max(1, (max_ore + 23) // 24 + 1)
    raccolte = prossime_raccolte(conn, da=oggi, giorni=orizzonte_giorni)

    out: list[dict] = []
    for r in rows:
        if r["ultimo_inviato"] == oggi.isoformat():
            continue  # dedup giornaliera
        fid = r["frazione_id"]
        anticipo = int(r["anticipo_ore"])
        for racc in raccolte:
            if racc["frazione_id"] != fid:
                continue
            # raccolta = inizio giornata (00:00 locale) della data
            momento_raccolta = datetime.combine(
                date.fromisoformat(racc["data"]), datetime.min.time()
            )
            delta_ore = (momento_raccolta - now).total_seconds() / 3600.0
            # entro l'anticipo (futuro) e fino a 24h dopo (raccolta odierna gia' iniziata)
            if -24 <= delta_ore <= anticipo:
                out.append({
                    "promemoria_id": r["promemoria_id"],
                    "frazione_id": fid,
                    "frazione": r["frazione"],
                    "data": racc["data"],
                    "anticipo_ore": anticipo,
                })
                break
    return out
