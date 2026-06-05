"""Scadenze Auto/Casa — Streamlit entrypoint v1.0.0.

CRUD funzionale + template italiani precaricati + lista ordinata per data
+ check-as-paid con storico. Local-first SQLite.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# Cross-recipe shared notifier (best-effort, no exception se non installato)
import sys as _sys
_GIVE_ROOT = Path(__file__).resolve().parents[3]
if str(_GIVE_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_GIVE_ROOT))
try:
    from core.shared.notifier import notify_os, is_available as _notifier_available
except ImportError:
    def notify_os(t, m): return False
    def _notifier_available(): return False

DB_PATH = Path.home() / ".givengine" / "data" / "scadenze-auto-casa.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

TEMPLATE_ITALIANI = [
    ("auto", "Bollo auto", "ACI / Agenzia Entrate", 12),
    ("auto", "Revisione auto", "MCTC", 24),
    ("auto", "Assicurazione RCA", "Compagnia assicurativa", 12),
    ("auto", "Tagliando", "Officina", 12),
    ("casa", "Revisione caldaia", "Manutentore caldaia", 12),
    ("casa", "Pulizia camino", "Spazzacamino", 12),
    ("casa", "Assicurazione casa", "Compagnia assicurativa", 12),
    ("casa", "Disinfestazione", "Ditta servizi", 12),
    ("persona", "Patente di guida", "MCTC", 120),
    ("persona", "Passaporto", "Questura", 120),
    ("persona", "Visita medica generale", "Medico curante", 12),
    ("persona", "Dentista controllo", "Studio dentistico", 6),
]


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.row_factory = sqlite3.Row
    return conn


def list_scadenze(conn, prossime_giorni: int | None = None) -> list[dict]:
    cur = conn.cursor()
    if prossime_giorni is not None:
        limit_date = (date.today() + timedelta(days=prossime_giorni)).isoformat()
        cur.execute(
            "SELECT * FROM scadenze WHERE prossima_scadenza <= ? ORDER BY prossima_scadenza",
            (limit_date,),
        )
    else:
        cur.execute("SELECT * FROM scadenze ORDER BY prossima_scadenza")
    return [dict(r) for r in cur.fetchall()]


def _advance(d: date, frequenza_tipo: str, giorni) -> date | None:
    """Calcola la prossima scadenza dopo un pagamento.

    - 'mensile'    → +1 mese di CALENDARIO (gestisce fine mese)
    - 'custom'     → +N giorni
    - 'una-tantum' → None (non si ripete)
    """
    if frequenza_tipo == "mensile":
        from dateutil.relativedelta import relativedelta
        return d + relativedelta(months=1)
    if frequenza_tipo == "custom" and giorni:
        return d + timedelta(days=int(giorni))
    return None


def add_scadenza(conn, categoria, tipo, oggetto, prossima,
                 frequenza_tipo, frequenza_giorni, importo, note):
    conn.execute(
        """INSERT INTO scadenze
        (categoria, tipo, oggetto, prossima_scadenza, frequenza_tipo,
         frequenza_custom_giorni, importo_previsto_eur, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (categoria, tipo, oggetto, prossima.isoformat(), frequenza_tipo,
         int(frequenza_giorni) if frequenza_giorni else None, importo, note),
    )
    conn.commit()


def update_scadenza(conn, scadenza_id, categoria, tipo, oggetto, prossima,
                    frequenza_tipo, frequenza_giorni, importo, note) -> None:
    conn.execute(
        """UPDATE scadenze SET categoria=?, tipo=?, oggetto=?, prossima_scadenza=?,
           frequenza_tipo=?, frequenza_custom_giorni=?, importo_previsto_eur=?,
           note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (categoria, tipo, oggetto, prossima.isoformat(), frequenza_tipo,
         int(frequenza_giorni) if frequenza_giorni else None, importo, note, scadenza_id),
    )
    conn.commit()


def mark_paid(conn, scadenza_id: int, importo_pagato: float, metodo: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM scadenze WHERE id=?", (scadenza_id,))
    row = cur.fetchone()
    if not row:
        return
    conn.execute(
        """INSERT INTO pagamenti_storici
        (scadenza_id, data_pagamento, importo_pagato_eur, metodo)
        VALUES (?, ?, ?, ?)""",
        (scadenza_id, date.today().isoformat(), importo_pagato, metodo),
    )
    nuova = _advance(date.fromisoformat(row["prossima_scadenza"]),
                     row["frequenza_tipo"], row["frequenza_custom_giorni"])
    if nuova:
        conn.execute(
            "UPDATE scadenze SET prossima_scadenza=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (nuova.isoformat(), scadenza_id),
        )
    conn.commit()


def delete_scadenza(conn, scadenza_id: int):
    conn.execute("DELETE FROM scadenze WHERE id=?", (scadenza_id,))
    conn.commit()


def get_storico(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """SELECT p.*, s.tipo, s.categoria FROM pagamenti_storici p
        LEFT JOIN scadenze s ON p.scadenza_id=s.id
        ORDER BY p.data_pagamento DESC"""
    )
    return [dict(r) for r in cur.fetchall()]


_FREQ_OPZIONI = [
    "Ogni mese",
    "Ogni N giorni (personalizzato)",
    "Ogni 3 mesi",
    "Ogni 6 mesi",
    "Ogni 12 mesi",
    "Ogni 24 mesi",
    "Una tantum (non si ripete)",
]


def _freq_default_label(tipo, giorni) -> str:
    """Etichetta selezionata per una scadenza esistente (per il form modifica)."""
    if tipo == "mensile":
        return "Ogni mese"
    if tipo == "una-tantum" or not giorni:
        return "Una tantum (non si ripete)"
    for label, mesi in (("Ogni 3 mesi", 3), ("Ogni 6 mesi", 6),
                        ("Ogni 12 mesi", 12), ("Ogni 24 mesi", 24)):
        if int(giorni) == mesi * 30:
            return label
    return "Ogni N giorni (personalizzato)"


def _recurrence_inputs(key: str, def_label="Ogni mese", def_giorni=30):
    """Selettore 'si ripete ogni' usabile dentro un form. Ritorna (tipo, giorni).

    Il number_input dei giorni è sempre visibile (i form non fanno rerun finché
    non si invia) ma conta solo per l'opzione 'personalizzato'.
    """
    scelta = st.selectbox("Si ripete", _FREQ_OPZIONI,
                          index=_FREQ_OPZIONI.index(def_label), key=f"{key}_freq")
    giorni = st.number_input("…ogni quanti giorni (solo se 'personalizzato')",
                             min_value=1, value=int(def_giorni or 30), step=1, key=f"{key}_gg")
    if scelta == "Ogni mese":
        return "mensile", None
    if scelta == "Una tantum (non si ripete)":
        return "una-tantum", None
    if scelta == "Ogni N giorni (personalizzato)":
        return "custom", int(giorni)
    mesi = {"Ogni 3 mesi": 3, "Ogni 6 mesi": 6, "Ogni 12 mesi": 12, "Ogni 24 mesi": 24}[scelta]
    return "custom", mesi * 30


def main() -> None:
    st.set_page_config(page_title="Scadenze Auto/Casa", page_icon="📅", layout="wide")
    conn = get_conn()

    st.title("📅 Scadenze Auto/Casa")
    st.caption("Bollo, revisione, caldaia, assicurazione: non ti scordi più nulla")

    tab_oggi, tab_lista, tab_aggiungi, tab_storico, tab_template = st.tabs(
        ["⏰ Prossime", "📋 Tutte", "➕ Aggiungi", "📊 Storico pagamenti", "📋 Template ITA"]
    )

    with tab_oggi:
        _orizzonti = {"30 giorni": 30, "60 giorni": 60, "3 mesi": 90,
                      "6 mesi": 180, "1 anno": 365, "Tutte le future": 3650}
        oriz_label = st.selectbox("Mostra scadenze entro", list(_orizzonti),
                                  index=4, key="oriz_prossime")
        oriz_giorni = _orizzonti[oriz_label]
        prossime = list_scadenze(conn, prossime_giorni=oriz_giorni)
        # Notifica OS push per scadenze <=7 giorni (1 batch per session)
        if prossime and not st.session_state.get("_notified_today"):
            critiche = [r for r in prossime
                         if (date.fromisoformat(r["prossima_scadenza"]) - date.today()).days < 7]
            if critiche and _notifier_available():
                sent = notify_os(
                    f"⚠️ {len(critiche)} scadenze entro 7 giorni",
                    "; ".join(f"{r['tipo']} ({r['prossima_scadenza']})" for r in critiche[:3]),
                )
                if sent:
                    st.session_state["_notified_today"] = True
        if not prossime:
            st.info(f"Nessuna scadenza entro {oriz_label.lower()}. Aggiungi qualcosa nel tab '➕ Aggiungi'.")
        else:
            st.subheader(f"Scadenze entro {oriz_label.lower()}: {len(prossime)}")
            for r in prossime:
                giorni = (date.fromisoformat(r["prossima_scadenza"]) - date.today()).days
                color = "🔴" if giorni < 7 else ("🟠" if giorni < 30 else "🟢")
                with st.expander(f"{color} {r['tipo']} — {r['prossima_scadenza']} ({giorni} giorni)"):
                    st.write(f"**Categoria**: {r['categoria']}  •  **Oggetto**: {r['oggetto'] or '–'}")
                    if r["importo_previsto_eur"]:
                        st.write(f"**Importo previsto**: €{r['importo_previsto_eur']:.2f}")
                    if r["note"]:
                        st.write(f"**Note**: {r['note']}")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        imp = st.number_input("Importo pagato €", value=float(r["importo_previsto_eur"] or 0), key=f"imp_{r['id']}")
                    with c2:
                        met = st.selectbox("Metodo", ["bonifico", "carta", "contanti", "altro"], key=f"met_{r['id']}")
                    with c3:
                        st.write("")
                        if st.button("✓ Segna pagato", key=f"pay_{r['id']}"):
                            mark_paid(conn, r["id"], imp, met)
                            st.success("Pagamento registrato + prossima scadenza calcolata")
                            st.rerun()

    with tab_lista:
        all_sc = list_scadenze(conn)
        if not all_sc:
            st.info("Nessuna scadenza salvata.")
        else:
            # st.dialog (modale) se disponibile, altrimenti fallback inline.
            _dialog = st.dialog if hasattr(st, "dialog") else (lambda *a, **k: (lambda fn: fn))
            _tipi3 = ["auto", "casa", "persona"]

            @_dialog("✏️ Modifica scadenza")
            def _dlg_edit(r):
                e_cat = st.selectbox("Categoria", _tipi3, index=_tipi3.index(r["categoria"]))
                e_tipo = st.text_input("Tipo *", value=r["tipo"])
                e_ogg = st.text_input("Oggetto/riferimento", value=r["oggetto"] or "")
                e_prox = st.date_input("Prossima scadenza *",
                                       value=date.fromisoformat(r["prossima_scadenza"]))
                e_ftipo, e_fgiorni = _recurrence_inputs(
                    "edit",
                    def_label=_freq_default_label(r["frequenza_tipo"], r["frequenza_custom_giorni"]),
                    def_giorni=r["frequenza_custom_giorni"] or 30)
                e_imp = st.number_input("Importo previsto €", min_value=0.0,
                                        value=float(r["importo_previsto_eur"] or 0.0))
                e_note = st.text_area("Note", value=r["note"] or "")
                if st.button("💾 Salva modifiche", type="primary"):
                    if not e_tipo:
                        st.error("Tipo è obbligatorio")
                        return
                    update_scadenza(conn, r["id"], e_cat, e_tipo, e_ogg or None, e_prox,
                                    e_ftipo, e_fgiorni, e_imp or None, e_note or None)
                    st.rerun()

            @_dialog("✓ Segna come pagata")
            def _dlg_pay(r):
                imp = st.number_input("Importo pagato €",
                                      value=float(r["importo_previsto_eur"] or 0.0))
                met = st.selectbox("Metodo", ["bonifico", "carta", "contanti", "altro"])
                st.caption("Registro il pagamento e calcolo la prossima scadenza.")
                if st.button("✓ Conferma pagamento", type="primary"):
                    mark_paid(conn, r["id"], imp, met)
                    st.rerun()

            @_dialog("🗑 Conferma cancellazione")
            def _dlg_del(r):
                st.warning(f"Cancellare **{r['tipo']}** ({r['prossima_scadenza']})? "
                           "L'operazione è irreversibile.")
                c1, c2 = st.columns(2)
                if c1.button("🗑 Sì, cancella", type="primary"):
                    delete_scadenza(conn, r["id"])
                    st.rerun()
                if c2.button("Annulla"):
                    st.rerun()

            st.caption(f"{len(all_sc)} scadenze — pulsanti per riga (modifica / paga / cancella).")
            head = st.columns([3, 2, 2, 1, 1, 1])
            for col, lab in zip(head, ["Tipo", "Scadenza", "€ previsto", "", "", ""]):
                col.markdown(f"**{lab}**" if lab else "")
            for r in all_sc:
                cols = st.columns([3, 2, 2, 1, 1, 1])
                cols[0].markdown(
                    f"{r['tipo']}  \n<small style='color:#94a3b8'>{r['categoria']} · "
                    f"{r['oggetto'] or '–'}</small>", unsafe_allow_html=True)
                cols[1].write(r["prossima_scadenza"])
                cols[2].write(f"€ {(r['importo_previsto_eur'] or 0):.2f}")
                if cols[3].button("✏️", key=f"row_edit_{r['id']}", help="Modifica"):
                    _dlg_edit(r)
                if cols[4].button("✓", key=f"row_pay_{r['id']}", help="Segna pagata"):
                    _dlg_pay(r)
                if cols[5].button("🗑", key=f"row_del_{r['id']}", help="Cancella"):
                    _dlg_del(r)

    with tab_aggiungi:
        st.subheader("Nuova scadenza")
        with st.form("add_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                categoria = st.selectbox("Categoria", ["auto", "casa", "persona"])
                tipo = st.text_input("Tipo *", placeholder="Es. Bollo auto")
                oggetto = st.text_input("Oggetto/riferimento", placeholder="Es. Targa AB123CD")
            with c2:
                prossima = st.date_input("Prossima scadenza *", value=date.today() + timedelta(days=30))
                freq_tipo, freq_giorni = _recurrence_inputs("add")
                importo = st.number_input("Importo previsto €", min_value=0.0, value=0.0)
            note = st.text_area("Note", placeholder="Eventuali dettagli")
            if st.form_submit_button("➕ Aggiungi scadenza", type="primary"):
                if tipo:
                    add_scadenza(conn, categoria, tipo, oggetto, prossima,
                                 freq_tipo, freq_giorni, importo or None, note or None)
                    st.success(f"Scadenza '{tipo}' aggiunta")
                    st.rerun()
                else:
                    st.error("Tipo è obbligatorio")

    with tab_storico:
        storico = get_storico(conn)
        if storico:
            df = pd.DataFrame(storico)
            df_show = df[["data_pagamento", "tipo", "categoria", "importo_pagato_eur", "metodo"]].copy()
            df_show.columns = ["Data", "Tipo", "Categoria", "€ pagato", "Metodo"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            tot = df["importo_pagato_eur"].sum()
            st.metric("Totale storico pagamenti", f"€ {tot:.2f}")
        else:
            st.info("Nessun pagamento registrato. Segna come pagata una scadenza nel tab ⏰ Prossime.")

    with tab_template:
        st.subheader("Template scadenze italiane precaricati")
        st.caption("Click per aggiungere alla tua lista")
        for cat, tipo, oggetto, freq in TEMPLATE_ITALIANI:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"**[{cat}]** {tipo} — ogni {freq} mesi (default _{oggetto}_)")
            with c2:
                if st.button("➕", key=f"tpl_{tipo}_{cat}"):
                    next_date = date.today() + timedelta(days=int(freq * 30))
                    add_scadenza(conn, cat, tipo, oggetto, next_date,
                                 "custom", int(freq * 30), None, None)
                    st.toast(f"Aggiunto: {tipo}")
                    st.rerun()


if __name__ == "__main__":
    main()
