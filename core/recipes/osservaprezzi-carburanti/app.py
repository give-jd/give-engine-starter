"""Osservaprezzi Carburanti — Streamlit entrypoint v1.0.0.

Consultazione prezzi distributori carburanti italiani.
Source: CSV pubblico MIMIT (Ministero Imprese e Made in Italy).
Refresh on-demand + cache locale + diario rifornimenti personale.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Componente opzionale: geolocalizzazione del dispositivo via browser.
try:
    from streamlit_geolocation import streamlit_geolocation
    _HAS_GEO = True
except ImportError:  # pragma: no cover - dipende dall'installazione ricetta
    _HAS_GEO = False

DB_PATH = Path.home() / ".givengine" / "data" / "osservaprezzi-carburanti.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

MIMIT_ANAGRAFICA = "https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
MIMIT_PREZZI = "https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.row_factory = sqlite3.Row
    return conn


def _sniff_delim(header: str) -> str:
    """Rileva il separatore del CSV MIMIT dalla riga di intestazione.

    I file MIMIT usano la pipe `|` (storicamente a volte `;`): scegliamo quello
    che compare di più, così l'import non si rompe se cambiano formato.
    """
    return "|" if header.count("|") >= header.count(";") else ";"


def refresh_mimit(conn) -> dict:
    import httpx
    stats = {"esito": "ok", "anag": 0, "prezzi": 0}
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            r = client.get(MIMIT_ANAGRAFICA)
            r.raise_for_status()
            lines = r.text.splitlines()[1:]
            reader = csv.DictReader(io.StringIO("\n".join(lines)),
                                    delimiter=_sniff_delim(lines[0] if lines else ""))
            for row in reader:
                try:
                    conn.execute(
                        """INSERT OR REPLACE INTO distributori
                        (id, bandiera, tipo_impianto, nome_impianto, indirizzo,
                         comune, provincia, latitudine, longitudine, ultimo_aggiornamento_anagrafica)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (int(row.get("idImpianto", 0)),
                         row.get("Bandiera"), row.get("Tipo Impianto"),
                         row.get("Nome Impianto"), row.get("Indirizzo"),
                         row.get("Comune"), row.get("Provincia"),
                         float(row["Latitudine"]) if row.get("Latitudine") else None,
                         float(row["Longitudine"]) if row.get("Longitudine") else None,
                         date.today().isoformat()),
                    )
                    stats["anag"] += 1
                except (ValueError, KeyError):
                    continue
            conn.commit()
            r = client.get(MIMIT_PREZZI)
            r.raise_for_status()
            lines = r.text.splitlines()[1:]
            reader = csv.DictReader(io.StringIO("\n".join(lines)),
                                    delimiter=_sniff_delim(lines[0] if lines else ""))
            for row in reader:
                try:
                    is_self = str(row.get("isSelf", "")).strip() in ("1", "True", "true")
                    prezzo_val = float(row["prezzo"]) if row.get("prezzo") else None
                    conn.execute(
                        """INSERT OR IGNORE INTO prezzi
                        (distributore_id, carburante, prezzo_self, prezzo_servito, data_comunicazione)
                        VALUES (?, ?, ?, ?, ?)""",
                        (int(row.get("idImpianto", 0)),
                         row.get("descCarburante"),
                         prezzo_val if is_self else None,
                         prezzo_val if not is_self else None,
                         row.get("dtComu") or datetime.now().isoformat()),
                    )
                    stats["prezzi"] += 1
                except (ValueError, KeyError):
                    continue
            conn.commit()
    except Exception as e:
        stats["esito"] = f"error: {type(e).__name__}: {str(e)[:200]}"
    conn.execute(
        "INSERT INTO refresh_mimit (data_refresh, esito, righe_anagrafica, righe_prezzi) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), stats["esito"], stats["anag"], stats["prezzi"]),
    )
    conn.commit()
    return stats


def search_distributori(conn, comune: str, carburante: str = "Benzina") -> list[dict]:
    cur = conn.execute(
        """SELECT d.*, p.prezzo_self, p.prezzo_servito, p.data_comunicazione
        FROM distributori d
        LEFT JOIN prezzi p ON p.distributore_id=d.id AND p.carburante=?
        WHERE LOWER(d.comune) LIKE ?
        ORDER BY p.prezzo_self ASC NULLS LAST
        LIMIT 50""",
        (carburante, f"%{comune.lower()}%"),
    )
    return [dict(r) for r in cur.fetchall()]


def nearest_by_coords(conn, lat: float, lon: float, carburante: str, radius_km: float = 10.0, limit: int = 20) -> list[dict]:
    """Distributori entro radius_km da (lat,lon), ordinati per distanza.
    Usa bounding box pre-filter + Haversine actual distance.
    """
    import math
    # Bounding box approx (1° lat ~ 111km; 1° lon = 111km * cos(lat))
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    cur = conn.execute(
        """SELECT d.*, p.prezzo_self, p.prezzo_servito, p.data_comunicazione
        FROM distributori d
        LEFT JOIN prezzi p ON p.distributore_id=d.id AND p.carburante=?
        WHERE d.latitudine BETWEEN ? AND ?
          AND d.longitudine BETWEEN ? AND ?""",
        (carburante, lat - dlat, lat + dlat, lon - dlon, lon + dlon),
    )
    results = []
    for r in cur.fetchall():
        d = dict(r)
        # Haversine
        lat2, lon2 = d.get("latitudine"), d.get("longitudine")
        if lat2 is None or lon2 is None:
            continue
        rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat, lon, lat2, lon2])
        a = math.sin((rlat2 - rlat1)/2)**2 + math.cos(rlat1) * math.cos(rlat2) * math.sin((rlon2 - rlon1)/2)**2
        d["distanza_km"] = round(2 * 6371 * math.asin(math.sqrt(a)), 2)
        if d["distanza_km"] <= radius_km:
            results.append(d)
    results.sort(key=lambda x: x["distanza_km"])
    return results[:limit]


def add_rifornimento(conn, dist_id, data_r, carburante, litri, prezzo_unit, km, note):
    conn.execute(
        """INSERT INTO rifornimenti (distributore_id, data, carburante, litri,
        prezzo_unitario, prezzo_totale, km_attuali, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (dist_id, data_r.isoformat(), carburante, litri, prezzo_unit,
         litri * prezzo_unit if litri and prezzo_unit else None, km, note),
    )
    conn.commit()


def list_rifornimenti(conn) -> list[dict]:
    cur = conn.execute(
        """SELECT r.*, d.nome_impianto, d.comune FROM rifornimenti r
        LEFT JOIN distributori d ON r.distributore_id=d.id
        ORDER BY r.data DESC"""
    )
    return [dict(r) for r in cur.fetchall()]


def main() -> None:
    st.set_page_config(page_title="Osservaprezzi Carburanti", page_icon="⛽", layout="wide")
    conn = get_conn()

    st.title("⛽ Osservaprezzi Carburanti")
    st.caption("Prezzi distributori italiani dal MIMIT. Niente API key, dati pubblici.")

    tab_nearest, tab_search, tab_refill, tab_storico, tab_refresh = st.tabs(
        ["📍 Vicino a me", "🔍 Cerca per comune", "📝 Diario rifornimenti", "📊 Storico", "🔄 Refresh MIMIT"]
    )

    with tab_search:
        c1, c2 = st.columns([2, 1])
        with c1:
            comune = st.text_input("Comune", placeholder="Es. Milano")
        with c2:
            carburante = st.selectbox("Carburante", ["Benzina", "Gasolio", "GPL", "Metano"])
        if st.button("🔍 Cerca", type="primary"):
            if not comune.strip():
                st.warning("Inserisci un comune")
            else:
                results = search_distributori(conn, comune.strip(), carburante)
                if not results:
                    st.info("Nessun distributore trovato. Hai fatto un refresh recente? (tab 🔄)")
                else:
                    df = pd.DataFrame(results)
                    df_show = df[["nome_impianto", "bandiera", "indirizzo", "comune",
                                   "prezzo_self", "prezzo_servito", "data_comunicazione"]].copy()
                    df_show.columns = ["Impianto", "Bandiera", "Indirizzo", "Comune",
                                        "Self €", "Servito €", "Aggiornato"]
                    st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tab_nearest:
        st.subheader("📍 Distributori nelle vicinanze (geo)")
        if _HAS_GEO:
            st.caption("Premi l'icona per rilevare automaticamente la posizione del dispositivo, "
                       "oppure inserisci le coordinate a mano.")
            loc = streamlit_geolocation()
            if loc and loc.get("latitude") is not None and loc.get("longitude") is not None:
                st.session_state["geo_lat"] = float(loc["latitude"])
                st.session_state["geo_lon"] = float(loc["longitude"])
                st.success(f"Posizione rilevata: {loc['latitude']:.5f}, {loc['longitude']:.5f}")
        else:
            st.caption("Inserisci le tue coordinate GPS. Carburante + raggio personalizzabili.")
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            lat = st.number_input("Latitudine", value=st.session_state.get("geo_lat", 45.4642),
                                  format="%.6f", help="Es. Milano 45.4642")
        with c2:
            lon = st.number_input("Longitudine", value=st.session_state.get("geo_lon", 9.1900),
                                  format="%.6f", help="Es. Milano 9.1900")
        with c3:
            radius = st.number_input("Raggio km", min_value=1.0, max_value=50.0, value=10.0, step=1.0)
        carb_n = st.selectbox("Carburante  ", ["Benzina", "Gasolio", "GPL", "Metano"], key="nearest_carb")
        if st.button("📍 Cerca vicini", type="primary"):
            results = nearest_by_coords(conn, lat, lon, carb_n, radius)
            if not results:
                st.info("Nessun distributore in zona. Espandi raggio o fai refresh MIMIT.")
            else:
                df = pd.DataFrame(results)
                df_show = df[["distanza_km", "nome_impianto", "bandiera", "indirizzo",
                                "comune", "prezzo_self", "prezzo_servito"]].copy()
                df_show.columns = ["Km", "Impianto", "Bandiera", "Indirizzo", "Comune", "Self €", "Servito €"]
                st.dataframe(df_show, use_container_width=True, hide_index=True)
                if results:
                    cheapest = min((r for r in results if r.get("prezzo_self")),
                                    key=lambda x: x["prezzo_self"], default=None)
                    if cheapest:
                        st.success(f"💰 Più conveniente: **{cheapest['nome_impianto']}** ({cheapest['comune']}) a {cheapest['distanza_km']}km — €{cheapest['prezzo_self']:.3f}/L self")

    with tab_refill:
        st.subheader("Aggiungi rifornimento")
        with st.form("refill_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                data_r = st.date_input("Data", value=date.today())
                carb = st.selectbox("Carburante ", ["Benzina", "Gasolio", "GPL", "Metano"])
                litri = st.number_input("Litri", min_value=0.0, value=0.0, step=0.01)
            with c2:
                prezzo = st.number_input("Prezzo €/litro", min_value=0.0, value=0.0, step=0.001, format="%.3f")
                km = st.number_input("Km attuali", min_value=0, value=0)
                dist_id = st.number_input("ID distributore (opzionale)", min_value=0, value=0)
            note = st.text_input("Note", placeholder="Es. Pieno autostrada")
            if st.form_submit_button("⛽ Registra rifornimento", type="primary"):
                if litri > 0 and prezzo > 0:
                    add_rifornimento(conn, dist_id or None, data_r, carb, litri, prezzo, km or None, note or None)
                    st.success(f"Rifornimento {litri:.2f}L × €{prezzo:.3f} = €{litri*prezzo:.2f}")
                    st.rerun()
                else:
                    st.error("Litri e prezzo > 0 obbligatori")

    with tab_storico:
        rif = list_rifornimenti(conn)
        if rif:
            df = pd.DataFrame(rif)
            df["data"] = pd.to_datetime(df["data"])
            df_show = df[["data", "carburante", "litri", "prezzo_unitario", "prezzo_totale", "km_attuali", "nome_impianto"]].copy()
            df_show.columns = ["Data", "Carb", "Litri", "€/L", "Totale €", "Km", "Impianto"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            with c1:
                tot_eur = df["prezzo_totale"].sum()
                st.metric("Spesa totale", f"€ {tot_eur:.2f}")
            with c2:
                tot_l = df["litri"].sum()
                if tot_l > 0:
                    st.metric("Media €/L", f"€ {tot_eur/tot_l:.3f}")
        else:
            st.info("Nessun rifornimento registrato.")

    with tab_refresh:
        st.subheader("Refresh dati MIMIT")
        st.caption("Scarica anagrafica + prezzi correnti dal CSV pubblico MIMIT. Tempo: 10-30 secondi (~25k impianti).")
        cur = conn.execute("SELECT * FROM refresh_mimit ORDER BY data_refresh DESC LIMIT 5")
        ultimi = [dict(r) for r in cur.fetchall()]
        if ultimi:
            st.subheader("Ultimi refresh")
            df = pd.DataFrame(ultimi)[["data_refresh", "esito", "righe_anagrafica", "righe_prezzi"]]
            st.dataframe(df, use_container_width=True, hide_index=True)
        if st.button("🔄 Avvia refresh ora", type="primary"):
            with st.spinner("Download MIMIT in corso..."):
                stats = refresh_mimit(conn)
            if stats["esito"] == "ok":
                st.success(f"✓ {stats['anag']} impianti + {stats['prezzi']} prezzi aggiornati")
            else:
                st.error(stats["esito"])


if __name__ == "__main__":
    main()
