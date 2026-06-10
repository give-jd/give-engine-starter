"""Calendario Rifiuti Comunale — Streamlit entrypoint v1.0.0.

Local-first: costruisci il calendario della raccolta differenziata del tuo comune,
calcola le prossime raccolte, ricevi promemoria OS e consulta il regolamento
"dove butto X". Nessun dato esce dal PC; AI solo BYOK opt-in.

REGOLA: nessuna chiamata ``st.*`` a import-time. Tutto dentro funzioni / ``main()``.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

# Root del monorepo per importare core.shared.*
_GIVE_ROOT = Path(__file__).resolve().parents[3]
if str(_GIVE_ROOT) not in sys.path:
    sys.path.insert(0, str(_GIVE_ROOT))

# Dir ricetta per importare i moduli locali
_RECIPE_DIR = Path(__file__).resolve().parent
if str(_RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(_RECIPE_DIR))

from modules import riferimenti, services  # noqa: E402
from parsers import detect_parser, estrai_testo  # noqa: E402

# Notifier condiviso (best-effort, no eccezione se assente)
try:
    from core.shared.notifier import is_available as _notifier_available
    from core.shared.notifier import notify_os
except ImportError:  # pragma: no cover - degradazione
    def notify_os(t: str, m: str) -> bool:  # type: ignore
        return False

    def _notifier_available() -> bool:  # type: ignore
        return False

DB_PATH = Path.home() / ".givengine" / "data" / "calendario-comunale-rifiuti.db"
SCHEMA_PATH = _RECIPE_DIR / "schema.sql"


def get_conn() -> sqlite3.Connection:
    """Apre la connessione SQLite locale, creando lo schema se assente."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    services.init_db(conn)
    return conn


# --- Tab: Oggi / Prossime ---


def render_oggi(st, conn: sqlite3.Connection) -> None:
    st.subheader("Oggi e prossime raccolte")
    giorni = st.slider("Finestra (giorni)", 1, 30, 7)
    raccolte = services.prossime_raccolte(conn, da=date.today(), giorni=giorni)
    if not raccolte:
        st.info("Nessuna raccolta nella finestra. Aggiungi frazioni e ricorrenze "
                "dalla tab Importa.")
        return
    for r in raccolte:
        st.write(f"**{r['data']}** — {r['frazione']} ({r['tipo']})")

    if not _notifier_available():
        st.warning("Notifiche di sistema non disponibili: vedrai le scadenze qui.")
    if st.button("Invia promemoria ora"):
        da_inviare = services.promemoria_da_inviare(conn, now=datetime.now())
        inviati = 0
        for p in da_inviare:
            if notify_os("Raccolta rifiuti", f"{p['frazione']} il {p['data']}"):
                services.marca_promemoria_inviato(conn, p["promemoria_id"], date.today())
                inviati += 1
        st.success(f"Promemoria inviati: {inviati}")


# --- Tab: Calendario ---


def render_calendario(st, conn: sqlite3.Connection) -> None:
    st.subheader("Calendario del mese")
    raccolte = services.prossime_raccolte(conn, da=date.today(), giorni=31)
    if not raccolte:
        st.info("Calendario vuoto.")
        return
    for r in raccolte:
        st.write(f"{r['data']}: {r['frazione']}")


# --- Tab: Importa ---


def render_importa(st, conn: sqlite3.Connection) -> None:
    st.subheader("Importa il calendario")
    st.caption(riferimenti.DISCLAIMER)
    modo = st.radio("Modalita'", ["Manuale guidato", "PDF assistito", "AI (opt-in)"])

    if modo == "Manuale guidato":
        _render_manuale(st, conn)
    elif modo == "PDF assistito":
        _render_pdf(st, conn)
    else:
        _render_ai(st, conn)


def _render_manuale(st, conn: sqlite3.Connection) -> None:
    nomi = [f["nome"] for f in riferimenti.FRAZIONI_PRESET]
    scelta = st.selectbox("Frazione", nomi)
    tipo = st.selectbox("Ricorrenza",
                        ["settimanale", "quindicinale", "mensile", "lista_date"])
    if st.button("Aggiungi frazione + ricorrenza"):
        preset = riferimenti.frazione_preset(scelta) or {}
        fid = services.add_frazione(conn, {
            "nome": scelta, "colore": preset.get("colore"), "icona": preset.get("icona"),
        })
        st.session_state["ultima_frazione_id"] = fid
        st.success(f"Frazione '{scelta}' creata. Configura la ricorrenza ({tipo}).")


def _render_pdf(st, conn: sqlite3.Connection) -> None:
    up = st.file_uploader("Carica il PDF del calendario comunale", type=["pdf"])
    if up is None:
        return
    testo = estrai_testo(up.getvalue())
    if not testo:
        st.warning("Non riesco a leggere il testo del PDF (forse e' una scansione). "
                   "Usa la modalita' Manuale guidato.")
        return
    parser = detect_parser(testo)
    if parser is None:
        st.warning("Formato non riconosciuto. Verifica a mano in Manuale guidato.")
        return
    cal = parser.parse(testo)
    st.session_state["parsed_calendar"] = cal.to_dict()
    st.info(f"Riconosciute {len(cal.ricorrenze)} ricorrenze (parser {cal.parser_usato}). "
            "Verificale prima di salvare.")
    for r in cal.ricorrenze:
        st.write(f"- {r.frazione}: {r.tipo} {r.giorni_settimana or r.date_extra or ''}")


def _render_ai(st, conn: sqlite3.Connection) -> None:
    from parsers import ai_extract

    key = st.session_state.get("byok_key")
    if not key or not ai_extract.is_available():
        st.warning("L'estrazione AI e' opzionale (BYOK). Imposta la tua chiave in "
                   "Impostazioni, oppure usa Manuale guidato / PDF assistito.")
        return
    st.info("AI BYOK attiva (opt-in). L'estrazione completa arriva in v1.1.")


# --- Tab: Regolamento ---


def render_regolamento(st, conn: sqlite3.Connection) -> None:
    st.subheader("Dove butto X?")
    st.caption(riferimenti.DISCLAIMER)
    q = st.text_input("Cerca un materiale (es. 'bottiglia di vetro')")
    if q:
        risultati = services.cerca_materiale(conn, q)
        if risultati:
            for r in risultati:
                st.write(f"**{r['materiale']}** -> {r['frazione'] or 'non assegnata'} "
                         f"({r.get('note') or ''})")
        else:
            st.info("Nessuna corrispondenza nel tuo regolamento.")

    # Camera opt-in (BYOK)
    from parsers import ai_extract
    if st.session_state.get("byok_key") and ai_extract.is_available():
        foto = st.camera_input("Inquadra il rifiuto (opzionale)")
        if foto is not None:
            etichetta = ai_extract.classifica_foto(foto.getvalue(),
                                                   st.session_state.get("byok_key"))
            if etichetta:
                st.write(f"Materiale rilevato: {etichetta}. Verifica il regolamento "
                         "del tuo comune.")
            else:
                st.info("Riconoscimento non disponibile in questa versione.")
    else:
        st.caption("Riconoscimento da foto disponibile come opzione AI (BYOK).")


# --- Tab: Impostazioni ---


def render_impostazioni(st, conn: sqlite3.Connection) -> None:
    st.subheader("Impostazioni")
    comune = st.text_input("Comune", value=st.session_state.get("comune", ""))
    if comune:
        st.session_state["comune"] = comune
    key = st.text_input("Chiave AI (BYOK, opzionale)", type="password")
    if key:
        st.session_state["byok_key"] = key
        st.success("Chiave salvata in sessione (non lascia il PC).")
    st.caption("Senza chiave AI l'app funziona comunque: manuale, PDF, ricerca testuale.")


def main() -> None:
    """Entrypoint Streamlit. Tutte le chiamate ``st.*`` vivono qui dentro."""
    import streamlit as st

    st.set_page_config(page_title="Calendario Rifiuti Comunale", page_icon="♻️")
    st.title("Calendario Rifiuti Comunale")
    conn = get_conn()
    tab_oggi, tab_cal, tab_imp, tab_reg, tab_set = st.tabs(
        ["Oggi/Prossime", "Calendario", "Importa", "Regolamento", "Impostazioni"]
    )
    with tab_oggi:
        render_oggi(st, conn)
    with tab_cal:
        render_calendario(st, conn)
    with tab_imp:
        render_importa(st, conn)
    with tab_reg:
        render_regolamento(st, conn)
    with tab_set:
        render_impostazioni(st, conn)


if __name__ == "__main__":
    main()
