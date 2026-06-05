"""Letture Contatori — Streamlit entrypoint v1.0.0.

CRUD letture utenze (gas/luce/acqua) + dashboard storico + alert finestre
auto-lettura ARERA. Local-first SQLite.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path.home() / ".givengine" / "data" / "letture-contatori.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
# Integrazione opzionale con ricette sorelle (DB nella stessa cartella, read-only).
BOLLETTE_DB = DB_PATH.parent / "bollette-watcher.db"
SCADENZE_DB = DB_PATH.parent / "scadenze-auto-casa.db"

UNITA_DEFAULT = {"gas": "smc", "luce": "kWh", "acqua": "mc"}
ARERA_GAS_WINDOW = (25, 5)


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.row_factory = sqlite3.Row
    return conn


def list_utenze(conn) -> list[dict]:
    cur = conn.execute("SELECT * FROM utenze ORDER BY tipo, alias_utente")
    return [dict(r) for r in cur.fetchall()]


def add_utenza(conn, tipo, codice, fornitore, alias, fasce):
    conn.execute(
        """INSERT INTO utenze
        (tipo, codice_pod_pdr, fornitore_attuale, unita_misura,
         fasce_orarie_attive, alias_utente)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (tipo, codice, fornitore, UNITA_DEFAULT[tipo], 1 if fasce else 0, alias),
    )
    conn.commit()


def add_lettura(conn, utenza_id, data_lettura, valore, f1, f2, f3, note, foto_path=None):
    conn.execute(
        """INSERT INTO letture
        (utenza_id, data_lettura, valore, valore_f1, valore_f2, valore_f3,
         tipo_lettura, foto_path, note)
        VALUES (?, ?, ?, ?, ?, ?, 'autolettura', ?, ?)""",
        (utenza_id, data_lettura.isoformat(), valore, f1, f2, f3, foto_path, note),
    )
    conn.commit()


def save_photo(utenza_id: int, file_obj) -> str:
    """Salva foto contatore in ~/.givengine/data/letture-photos/<utenza>/. Returns path."""
    photo_dir = DB_PATH.parent / "letture-photos" / str(utenza_id)
    photo_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fp = photo_dir / f"{ts}_{file_obj.name}"
    fp.write_bytes(file_obj.getbuffer())
    return str(fp)


def list_letture(conn, utenza_id: int | None = None) -> list[dict]:
    if utenza_id:
        cur = conn.execute(
            """SELECT l.*, u.tipo, u.unita_misura, u.alias_utente
            FROM letture l JOIN utenze u ON l.utenza_id=u.id
            WHERE l.utenza_id=? ORDER BY l.data_lettura DESC""",
            (utenza_id,),
        )
    else:
        cur = conn.execute(
            """SELECT l.*, u.tipo, u.unita_misura, u.alias_utente
            FROM letture l JOIN utenze u ON l.utenza_id=u.id
            ORDER BY l.data_lettura DESC LIMIT 100"""
        )
    return [dict(r) for r in cur.fetchall()]


def calcola_consumi(letture: list[dict]) -> pd.DataFrame:
    if not letture:
        return pd.DataFrame()
    df = pd.DataFrame(letture)
    df["data_lettura"] = pd.to_datetime(df["data_lettura"])
    df = df.sort_values("data_lettura").reset_index(drop=True)
    df["consumo"] = df["valore"].diff()
    df["giorni"] = df["data_lettura"].diff().dt.days
    df["consumo_giornaliero"] = df["consumo"] / df["giorni"]
    return df


def read_bollette_readings() -> list[dict]:
    """Legge le letture assolute dalle bollette importate in Bollette Watcher.

    Apre il DB sorella in sola lettura; tollera assenza DB o schema vecchio.
    Ritorna una lista di dict con tipo/pod_pdr/fornitore/data/valore/unita.
    """
    if not BOLLETTE_DB.exists():
        return []
    try:
        bc = sqlite3.connect(f"file:{BOLLETTE_DB}?mode=ro", uri=True)
        bc.row_factory = sqlite3.Row
        cols = {r[1] for r in bc.execute("PRAGMA table_info(bollette)")}
        if "lettura_att" not in cols:
            bc.close()
            return []
        rows = bc.execute(
            """SELECT b.lettura_prec, b.lettura_prec_data,
                      b.lettura_att, b.lettura_att_data, b.consumo_unita,
                      u.tipo, u.pod_pdr, u.fornitore, u.alias
               FROM bollette b JOIN utenze u ON b.utenza_id = u.id
               WHERE u.tipo IN ('gas', 'luce', 'acqua')
                 AND (b.lettura_att IS NOT NULL OR b.lettura_prec IS NOT NULL)"""
        ).fetchall()
        bc.close()
    except sqlite3.Error:
        return []

    out: list[dict] = []
    seen: set = set()
    for r in rows:
        for val, dat in ((r["lettura_prec"], r["lettura_prec_data"]),
                         (r["lettura_att"], r["lettura_att_data"])):
            if val is None or not dat:
                continue
            key = (r["tipo"], r["pod_pdr"], dat, float(val))
            if key in seen:
                continue
            seen.add(key)
            out.append({"tipo": r["tipo"], "pod_pdr": r["pod_pdr"] or "",
                        "fornitore": r["fornitore"], "alias_src": r["alias"],
                        "data": dat, "valore": float(val),
                        "unita": r["consumo_unita"]})
    out.sort(key=lambda x: x["data"])
    return out


def read_bollette_utenze() -> list[dict]:
    """Utenze gas/luce/acqua configurate nella ricetta Bollette Watcher (read-only)."""
    if not BOLLETTE_DB.exists():
        return []
    try:
        bc = sqlite3.connect(f"file:{BOLLETTE_DB}?mode=ro", uri=True)
        bc.row_factory = sqlite3.Row
        rows = bc.execute(
            "SELECT alias, tipo, fornitore, pod_pdr FROM utenze "
            "WHERE tipo IN ('gas', 'luce', 'acqua') ORDER BY tipo, alias"
        ).fetchall()
        bc.close()
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]


def read_scadenze_auto_casa() -> list[dict]:
    """Scadenze dalla ricetta Scadenze auto/casa (read-only), se installata."""
    if not SCADENZE_DB.exists():
        return []
    try:
        sc = sqlite3.connect(f"file:{SCADENZE_DB}?mode=ro", uri=True)
        sc.row_factory = sqlite3.Row
        rows = sc.execute(
            "SELECT categoria, tipo, oggetto, prossima_scadenza, importo_previsto_eur "
            "FROM scadenze ORDER BY prossima_scadenza"
        ).fetchall()
        sc.close()
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]


def lettura_exists(conn, utenza_id: int, data_iso: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM letture WHERE utenza_id=? AND data_lettura=?",
        (utenza_id, data_iso)).fetchone()
    return r is not None


def add_lettura_fattura(conn, utenza_id: int, data_iso: str, valore: float) -> None:
    """Inserisce una lettura assoluta proveniente da una bolletta PDF."""
    conn.execute(
        """INSERT INTO letture
        (utenza_id, data_lettura, valore, tipo_lettura, note)
        VALUES (?, ?, ?, 'fattura', 'Importata da Bollette Watcher')""",
        (utenza_id, data_iso, valore))
    conn.commit()


def _match_utenza(cand: dict, utenze: list[dict]) -> int | None:
    """Match per POD/PDR + tipo; fallback: unica utenza dello stesso tipo."""
    if cand["pod_pdr"]:
        for u in utenze:
            if u["tipo"] == cand["tipo"] and (u["codice_pod_pdr"] or "") == cand["pod_pdr"]:
                return u["id"]
    same = [u for u in utenze if u["tipo"] == cand["tipo"]]
    return same[0]["id"] if len(same) == 1 else None


def main() -> None:
    st.set_page_config(page_title="Letture Contatori", page_icon="📊", layout="wide")
    conn = get_conn()

    st.title("📊 Letture Contatori")
    st.caption("Auto-letture gas/luce/acqua. Prepari le bollette, scopri i conguagli.")

    oggi = date.today()
    if oggi.day >= ARERA_GAS_WINDOW[0] or oggi.day <= ARERA_GAS_WINDOW[1]:
        st.success(f"🟢 **Finestra ARERA aperta**: giorno {oggi.day} → puoi comunicare l'auto-lettura gas al fornitore.")

    tab_letture, tab_aggiungi, tab_utenze, tab_scadenze, tab_dashboard = st.tabs(
        ["📋 Storico letture", "➕ Nuova lettura", "🏠 Utenze", "📅 Scadenze", "📈 Dashboard"]
    )

    utenze = list_utenze(conn)

    with tab_utenze:
        st.subheader("Le tue utenze")
        if utenze:
            df_u = pd.DataFrame(utenze)[["tipo", "alias_utente", "codice_pod_pdr",
                                          "fornitore_attuale", "unita_misura"]]
            df_u.columns = ["Tipo", "Alias", "POD/PDR", "Fornitore", "Unità"]
            st.dataframe(df_u, use_container_width=True, hide_index=True)
        else:
            st.info("Nessuna utenza configurata. Importala da Bollette Watcher o aggiungila a mano.")

        bw_utenze = read_bollette_utenze()
        if bw_utenze:
            with st.expander(f"📥 Importa utenze da Bollette Watcher ({len(bw_utenze)} trovate)"):
                existing = set()
                for u in utenze:
                    pod = (u["codice_pod_pdr"] or "").strip()
                    existing.add((u["tipo"], pod or f"alias:{u['alias_utente']}"))
                preview = []
                for b in bw_utenze:
                    pod = (b["pod_pdr"] or "").strip()
                    key = (b["tipo"], pod or f"alias:{b['alias']}")
                    preview.append({**b, "_key": key, "_new": key not in existing})
                df_bw = pd.DataFrame([{
                    "Tipo": p["tipo"], "Alias": p["alias"] or "—",
                    "POD/PDR": p["pod_pdr"] or "—", "Fornitore": p["fornitore"] or "—",
                    "Stato": "nuova" if p["_new"] else "già presente",
                } for p in preview])
                st.dataframe(df_bw, use_container_width=True, hide_index=True)
                n_new = sum(1 for p in preview if p["_new"])
                st.caption(f"{n_new} utenze nuove. Le già presenti non vengono duplicate. "
                           "Dopo l'import, usa l'import letture nello Storico.")
                if st.button("📥 Importa utenze nuove", type="primary", disabled=n_new == 0):
                    imp = 0
                    for p in preview:
                        if not p["_new"]:
                            continue
                        add_utenza(conn, p["tipo"], (p["pod_pdr"] or None),
                                   p["fornitore"] or None,
                                   p["alias"] or f"{p['tipo']} (da bolletta)", False)
                        imp += 1
                    st.success(f"Importate {imp} utenze da Bollette Watcher.")
                    st.rerun()

        st.divider()
        with st.form("add_utenza_form", clear_on_submit=True):
            st.subheader("Aggiungi utenza")
            c1, c2, c3 = st.columns(3)
            with c1:
                tipo = st.selectbox("Tipo", ["gas", "luce", "acqua"])
                alias = st.text_input("Alias", placeholder="Es. Casa Milano")
            with c2:
                codice = st.text_input("Codice POD/PDR", placeholder="14-17 cifre")
                fornitore = st.text_input("Fornitore", placeholder="Es. Enel, Eni, A2A")
            with c3:
                st.write("")
                fasce = st.checkbox("Fasce orarie attive (F1/F2/F3)")
            if st.form_submit_button("➕ Aggiungi utenza", type="primary"):
                if tipo and alias:
                    add_utenza(conn, tipo, codice or None, fornitore or None, alias, fasce)
                    st.success(f"Utenza '{alias}' aggiunta")
                    st.rerun()
                else:
                    st.error("Tipo e Alias obbligatori")

    with tab_scadenze:
        st.subheader("📅 Scadenze")
        st.caption("Scadenze dalla ricetta Scadenze auto/casa (sola lettura).")
        scadenze = read_scadenze_auto_casa()
        if not SCADENZE_DB.exists():
            st.info("Ricetta **Scadenze auto/casa** non rilevata. Installala e aggiungi "
                    "scadenze: compariranno qui.")
        elif not scadenze:
            st.info("Nessuna scadenza registrata in Scadenze auto/casa.")
        else:
            oggi = date.today()
            df_sc = pd.DataFrame([{
                "Scadenza": s["prossima_scadenza"],
                "Categoria": s["categoria"],
                "Tipo": s["tipo"],
                "Oggetto": s["oggetto"] or "—",
                "€ previsto": f"{(s['importo_previsto_eur'] or 0):.2f}",
                "Stato": "⚠ scaduta" if s["prossima_scadenza"] < oggi.isoformat() else "ok",
            } for s in scadenze])
            st.dataframe(df_sc, use_container_width=True, hide_index=True)
            st.caption("Per modificarle apri la ricetta Scadenze auto/casa.")

    with tab_aggiungi:
        if not utenze:
            st.warning("Aggiungi prima un'utenza nel tab 🏠 Utenze.")
        else:
            st.subheader("Nuova lettura")
            with st.form("add_lettura_form", clear_on_submit=True):
                ut_id = st.selectbox(
                    "Utenza",
                    [u["id"] for u in utenze],
                    format_func=lambda i: f"{next(u['tipo'] for u in utenze if u['id']==i)} — {next(u['alias_utente'] for u in utenze if u['id']==i)}",
                )
                data_l = st.date_input("Data lettura", value=date.today())
                utenza = next(u for u in utenze if u["id"] == ut_id)
                valore = st.number_input(f"Valore totale ({utenza['unita_misura']}) *",
                                         min_value=0.0, value=0.0, step=0.01)
                f1 = f2 = f3 = None
                if utenza["fasce_orarie_attive"]:
                    c1, c2, c3 = st.columns(3)
                    with c1: f1 = st.number_input("F1 (8-19 feriali)", min_value=0.0, value=0.0, step=0.01)
                    with c2: f2 = st.number_input("F2 (7-8 e 19-23 + sab)", min_value=0.0, value=0.0, step=0.01)
                    with c3: f3 = st.number_input("F3 (notte + festivi)", min_value=0.0, value=0.0, step=0.01)
                note = st.text_input("Note", placeholder="Eventuale anomalia/conferma fornitore")
                foto = st.file_uploader("📷 Foto contatore (opzionale)", type=["jpg", "jpeg", "png"])
                if st.form_submit_button("📝 Salva lettura", type="primary"):
                    if valore > 0:
                        foto_path = save_photo(ut_id, foto) if foto else None
                        add_lettura(conn, ut_id, data_l, valore, f1, f2, f3, note or None, foto_path)
                        st.success(f"Lettura salvata{' + foto' if foto_path else ''}")
                        st.rerun()
                    else:
                        st.error("Inserisci un valore > 0")

    with tab_letture:
        bollette_readings = read_bollette_readings()
        if bollette_readings:
            with st.expander(f"📥 Importa da Bollette Watcher ({len(bollette_readings)} letture trovate)"):
                if not utenze:
                    st.warning("Crea prima un'utenza nel tab 🏠 Utenze per importare le letture.")
                else:
                    preview = [{**c, "utenza_id": _match_utenza(c, utenze)}
                               for c in bollette_readings]
                    df_prev = pd.DataFrame([{
                        "Tipo": p["tipo"], "POD/PDR": p["pod_pdr"] or "—",
                        "Data": p["data"], "Valore": p["valore"],
                        "→ Utenza": next((u["alias_utente"] for u in utenze
                                          if u["id"] == p["utenza_id"]), "⚠️ nessun match"),
                    } for p in preview])
                    st.dataframe(df_prev, use_container_width=True, hide_index=True)
                    st.caption("Le letture senza match (POD/PDR diverso o più utenze stesso tipo) "
                               "vengono saltate. Importi già presenti non vengono duplicati.")
                    if st.button("📥 Importa letture compatibili", type="primary"):
                        imp = skip = 0
                        for p in preview:
                            if not p["utenza_id"] or lettura_exists(conn, p["utenza_id"], p["data"]):
                                skip += 1
                                continue
                            add_lettura_fattura(conn, p["utenza_id"], p["data"], p["valore"])
                            imp += 1
                        st.success(f"Importate {imp} letture · saltate {skip} (duplicate o senza match).")
                        st.rerun()

        letture = list_letture(conn)
        if letture:
            df = pd.DataFrame(letture)
            df_show = df[["data_lettura", "tipo", "alias_utente", "valore", "unita_misura", "note"]].copy()
            df_show.columns = ["Data", "Tipo", "Utenza", "Valore", "Unità", "Note"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.info("Nessuna lettura registrata.")

    with tab_dashboard:
        if not utenze:
            st.info("Aggiungi un'utenza + qualche lettura per vedere il consumo.")
        else:
            ut_id = st.selectbox(
                "Utenza per dashboard",
                [u["id"] for u in utenze],
                format_func=lambda i: f"{next(u['tipo'] for u in utenze if u['id']==i)} — {next(u['alias_utente'] for u in utenze if u['id']==i)}",
                key="dash_ut",
            )
            letture_u = list_letture(conn, ut_id)
            df = calcola_consumi(letture_u)
            if df.empty or len(df) < 2:
                st.info("Servono almeno 2 letture per calcolare il consumo.")
            else:
                utenza = next(u for u in utenze if u["id"] == ut_id)
                unita = utenza["unita_misura"]
                c1, c2, c3 = st.columns(3)
                with c1:
                    cons_tot = df["consumo"].dropna().sum()
                    st.metric(f"Consumo totale ({unita})", f"{cons_tot:.2f}")
                with c2:
                    cons_med = df["consumo_giornaliero"].dropna().mean()
                    st.metric(f"Media giornaliera ({unita})", f"{cons_med:.3f}")
                with c3:
                    ultima = df.iloc[-1]
                    st.metric("Ultima lettura", f"{ultima['valore']:.2f} {unita}",
                              delta=f"+{ultima['consumo']:.2f}" if ultima['consumo'] else None)
                st.line_chart(df.set_index("data_lettura")["valore"])


if __name__ == "__main__":
    main()
