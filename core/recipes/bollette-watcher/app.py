"""Bollette Watcher — Streamlit entrypoint."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import sys
from pathlib import Path

import streamlit as st

DATA_DIR  = Path(os.path.expanduser("~/.givengine/data"))
DB_PATH   = DATA_DIR / "bollette-watcher.db"
PREFS     = DATA_DIR / "bollette-watcher.prefs.json"
RECIPE_DIR = Path(__file__).resolve().parent
SCHEMA    = RECIPE_DIR / "schema.sql"

sys.path.insert(0, str(RECIPE_DIR))
from parsers import dispatch  # noqa: E402


def _init_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    # Migrazione idempotente: colonne letture assolute su DB pre-esistenti.
    cols = {r[1] for r in con.execute("PRAGMA table_info(bollette)")}
    for name, typ in (("lettura_prec", "REAL"), ("lettura_prec_data", "TEXT"),
                      ("lettura_att", "REAL"), ("lettura_att_data", "TEXT")):
        if name not in cols:
            con.execute(f"ALTER TABLE bollette ADD COLUMN {name} {typ}")
    con.commit()
    con.row_factory = sqlite3.Row
    return con


def _prefs_get(key: str, default=None):
    if not PREFS.exists():
        return default
    return json.loads(PREFS.read_text(encoding="utf-8")).get(key, default)


def _prefs_set(key: str, value) -> None:
    cur = {}
    if PREFS.exists():
        cur = json.loads(PREFS.read_text(encoding="utf-8"))
    cur[key] = value
    PREFS.parent.mkdir(parents=True, exist_ok=True)
    PREFS.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def show_privacy_gate():
    st.title("🔒 Bollette Watcher — Privacy")
    st.markdown((RECIPE_DIR / "PRIVACY.md").read_text(encoding="utf-8"))
    if st.checkbox("Ho letto e capito le informazioni privacy"):
        if st.button("Accetto e continuo →", type="primary"):
            _prefs_set("privacy_accepted_at", "now")
            st.rerun()
    st.stop()


def main():
    st.set_page_config(page_title="Bollette Watcher", layout="wide", page_icon="⚡")

    if not _prefs_get("privacy_accepted_at"):
        show_privacy_gate()

    con = _init_db()
    st.title("⚡ Bollette Watcher")
    st.caption("Dashboard locale dei tuoi consumi e costi · 100% sul tuo PC")

    tab_dash, tab_import, tab_settings = st.tabs(["Dashboard", "Importa PDF", "Impostazioni"])

    with tab_dash:
        st.subheader("Riepilogo utenze")
        rows = [dict(r) for r in con.execute("SELECT * FROM v_utenze_riepilogo").fetchall()]
        if not rows:
            st.info("Nessuna utenza ancora registrata. Vai su **Importa PDF** per cominciare.")
        else:
            st.dataframe(rows, use_container_width=True)
            ult = [dict(r) for r in con.execute(
                "SELECT b.imported_at, u.alias, u.tipo, b.periodo_inizio, b.periodo_fine, "
                "b.consumo_qta, b.consumo_unita, b.importo_totale, b.scadenza "
                "FROM bollette b JOIN utenze u ON u.id=b.utenza_id "
                "ORDER BY b.imported_at DESC LIMIT 50").fetchall()]
            if ult:
                st.subheader("Ultime bollette")
                st.dataframe(ult, use_container_width=True)

    with tab_import:
        st.subheader("Importa una bolletta PDF")
        f = st.file_uploader("Trascina qui il PDF", type=["pdf"])
        if f:
            try:
                from pdfminer.high_level import extract_text
            except ImportError:
                st.error("Manca `pdfminer.six`. Esegui `pip install pdfminer.six`.")
                st.stop()
            pdf_bytes = f.getvalue()
            file_hash = hashlib.sha256(pdf_bytes).hexdigest()
            text = extract_text(io.BytesIO(pdf_bytes))
            parsed = dispatch(text)
            st.success(f"Parser usato: **{parsed.parser_usato}** · confidence {parsed.confidence:.0%}")

            if con.execute("SELECT 1 FROM bollette WHERE file_hash=?", (file_hash,)).fetchone():
                st.info("Questo PDF è già stato importato. Lo trovi nella Dashboard.")
            else:
                _tipi = ["luce", "gas", "acqua", "telefono", "internet"]
                tipo_def = parsed.tipo if parsed.tipo in _tipi else "luce"
                with st.form("conferma_bolletta"):
                    st.caption("Controlla e correggi i dati rilevati, poi conferma.")
                    c1, c2 = st.columns(2)
                    with c1:
                        alias = st.text_input(
                            "Alias utenza",
                            value=((parsed.fornitore or "Utenza") + (f" {parsed.tipo}" if parsed.tipo else "")).strip())
                        tipo = st.selectbox("Tipo", _tipi, index=_tipi.index(tipo_def))
                        fornitore = st.text_input("Fornitore", value=parsed.fornitore or "")
                        pod_pdr = st.text_input("POD / PDR", value=parsed.pod_pdr or "")
                        intestatario = st.text_input("Intestatario", value=parsed.intestatario or "")
                    with c2:
                        periodo_inizio = st.text_input("Periodo dal", value=parsed.periodo_inizio or "")
                        periodo_fine = st.text_input("Periodo al", value=parsed.periodo_fine or "")
                        consumo_qta = st.number_input("Consumo", value=float(parsed.consumo_qta or 0.0), step=1.0)
                        consumo_unita = st.text_input("Unità consumo", value=parsed.consumo_unita or "")
                        importo_totale = st.number_input("Importo totale €", value=float(parsed.importo_totale or 0.0), step=0.01)
                        scadenza = st.text_input("Scadenza", value=parsed.scadenza or "")
                    if st.form_submit_button("✓ Conferma e salva", type="primary"):
                        row = con.execute(
                            "SELECT id FROM utenze WHERE alias=? AND tipo=?", (alias, tipo)).fetchone()
                        utenza_id = row["id"] if row else con.execute(
                            "INSERT INTO utenze (alias, tipo, fornitore, pod_pdr, intestatario) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (alias, tipo, fornitore or None, pod_pdr or None, intestatario or None)).lastrowid
                        con.execute(
                            """INSERT OR IGNORE INTO bollette
                            (utenza_id, file_originale, file_hash, periodo_inizio, periodo_fine,
                             consumo_qta, consumo_unita, lettura_prec, lettura_prec_data,
                             lettura_att, lettura_att_data, importo_totale, importo_imponibile, iva,
                             scadenza, parser_usato, confidence, raw_text)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (utenza_id, getattr(f, "name", None), file_hash,
                             periodo_inizio or None, periodo_fine or None,
                             consumo_qta or None, consumo_unita or None,
                             parsed.lettura_prec, parsed.lettura_prec_data,
                             parsed.lettura_att, parsed.lettura_att_data,
                             importo_totale or None, parsed.importo_imponibile, parsed.iva,
                             scadenza or None, parsed.parser_usato, parsed.confidence, text[:5000]))
                        con.commit()
                        st.success("Bolletta salvata. La trovi nella Dashboard.")
                        st.rerun()

            with st.expander("Dati grezzi rilevati dal parser"):
                st.json(parsed.to_dict())

    with tab_settings:
        st.subheader("Diritto all'oblio")
        st.warning("Cancella tutto: DB + cartella locale. Operazione irreversibile.")
        if st.button("🗑️ Cancella tutto", type="secondary"):
            if st.checkbox("Confermo, cancella tutto"):
                con.close()
                DB_PATH.unlink(missing_ok=True)
                PREFS.unlink(missing_ok=True)
                st.success("Cancellato. Chiudi e riapri la ricetta.")


if __name__ == "__main__":
    main()
