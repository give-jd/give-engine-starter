"""Curriculum Builder — wizard CV locale con anteprima live e 4 layout.

Tutto resta su questo PC: sqlite locale, zero chiamate esterne (Punto 14).
Avvio: streamlit run app.py --server.port 8627
"""

import base64
from pathlib import Path

from modules import anonymize, import_cv, render_cv, storage

TEMPLATES = Path(__file__).resolve().parent / "templates"
LAYOUTS = {"europass": "Europass", "moderno": "Moderno",
           "minimal": "Minimal ATS", "compatto": "Compatto"}
QCER = ["A1", "A2", "B1", "B2", "C1", "C2"]
STEPS = ["1. Dati personali", "2. Profilo", "3. Esperienze", "4. Istruzione",
         "5. Competenze", "6. Extra e note", "7. Trattamento dei dati", "8. Layout e lingua"]
PRIVACY_OPTS = {
    "standard-it": "Dicitura standard italiana (GDPR + D.Lgs. 196/2003)",
    "standard-en": "Standard English wording (GDPR)",
    "custom": "Testo personalizzato",
    "nessuna": "Nessuna dicitura",
}


def _css(layout: str) -> str:
    return ((TEMPLATES / "print-base.css").read_text(encoding="utf-8")
            + (TEMPLATES / f"cv-{layout}.css").read_text(encoding="utf-8"))


def _list_editor(st, items: list, blank, render_row, key: str) -> bool:
    """Righe con ▲ ▼ ✕ + Aggiungi. Ritorna True se la struttura è cambiata (serve rerun)."""
    changed = False
    for idx in range(len(items)):
        with st.container(border=True):
            c1, c2, c3, _ = st.columns([1, 1, 1, 6])
            if c1.button("▲", key=f"{key}-up-{idx}", disabled=idx == 0):
                items[idx - 1], items[idx] = items[idx], items[idx - 1]
                changed = True
            if c2.button("▼", key=f"{key}-dn-{idx}", disabled=idx == len(items) - 1):
                items[idx + 1], items[idx] = items[idx], items[idx + 1]
                changed = True
            if c3.button("✕", key=f"{key}-del-{idx}"):
                items.pop(idx)
                changed = True
                break
            if not changed:
                render_row(idx, items[idx])
    if st.button("+ Aggiungi", key=f"{key}-add"):
        items.append(blank())
        changed = True
    return changed


def _step_personali(st, d):
    with st.expander("📥 Importa da un CV esistente (PDF, Word, ODT)"):
        up = st.file_uploader("Carica il tuo CV", type=["pdf", "docx", "odt"], key="imp_file")
        ai_key = st.text_input("Chiave AI Anthropic — opzionale, BYOK (non lascia il PC)",
                               type="password", key="imp_key",
                               help="Senza chiave usa l'estrazione locale. Con la tua chiave la mappatura è più precisa.")
        if up is not None and st.button("Estrai e popola i campi"):
            text = None
            try:
                text = import_cv.extract_text(up.name, up.getvalue())
            except ValueError as e:
                st.error(str(e))
            except ImportError:
                st.error("Libreria per questo formato non disponibile su questa installazione.")
            if text:
                extracted = import_cv.parse_ai(text, ai_key) if ai_key else None
                if extracted is None:
                    extracted = import_cv.parse_heuristic(text)
                st.session_state.data = import_cv.apply_import(d, extracted)
                st.success("Campi popolati dal CV. L'estrazione è best-effort: controlla e correggi "
                           "i dati (specie ruolo/azienda e date) prima di stampare.")
                st.rerun()
        st.caption("L'estrazione del testo avviene sul tuo PC. La chiave AI è facoltativa; "
                   "se la usi, la chiamata parte dalla tua macchina con la tua chiave.")

    p = d["personal"]
    p["nome"] = st.text_input("Nome", p["nome"])
    p["cognome"] = st.text_input("Cognome", p["cognome"])
    p["email"] = st.text_input("Email", p["email"])
    p["tel"] = st.text_input("Telefono", p["tel"])
    p["indirizzo"] = st.text_input("Indirizzo", p["indirizzo"])
    p["dataNascita"] = st.text_input("Data di nascita (AAAA-MM-GG)", p["dataNascita"])
    p["nazionalita"] = st.text_input("Nazionalità", p["nazionalita"])
    p["linkedin"] = st.text_input("LinkedIn", p["linkedin"])
    p["sito"] = st.text_input("Sito web", p["sito"])
    foto = st.file_uploader("Foto (opzionale, resta su questo PC)", type=["png", "jpg", "jpeg", "webp"])
    if foto is not None:
        mime = foto.type or "image/jpeg"
        p["foto"] = f"data:{mime};base64,{base64.b64encode(foto.getvalue()).decode()}"
    if p["foto"] and st.button("Rimuovi foto"):
        p["foto"] = None
        st.rerun()


def _step_esperienze(st, d):
    def row(idx, x):
        x["ruolo"] = st.text_input("Ruolo", x["ruolo"], key=f"exp-ruolo-{idx}")
        x["azienda"] = st.text_input("Azienda", x["azienda"], key=f"exp-az-{idx}")
        x["luogo"] = st.text_input("Luogo", x["luogo"], key=f"exp-luogo-{idx}")
        x["dal"] = st.text_input("Dal (AAAA-MM)", x["dal"], key=f"exp-dal-{idx}")
        x["corrente"] = st.checkbox("Lavoro attuale", x["corrente"], key=f"exp-cur-{idx}")
        if not x["corrente"]:
            x["al"] = st.text_input("Al (AAAA-MM)", x["al"], key=f"exp-al-{idx}")
        x["descrizione"] = st.text_area("Descrizione", x["descrizione"], key=f"exp-desc-{idx}")

    if _list_editor(st, d["esperienze"],
                    lambda: {"ruolo": "", "azienda": "", "luogo": "", "dal": "", "al": "",
                             "corrente": False, "descrizione": ""}, row, "exp"):
        st.rerun()


def _step_istruzione(st, d):
    def row(idx, x):
        x["titolo"] = st.text_input("Titolo", x["titolo"], key=f"edu-tit-{idx}")
        x["istituto"] = st.text_input("Istituto", x["istituto"], key=f"edu-ist-{idx}")
        x["luogo"] = st.text_input("Luogo", x["luogo"], key=f"edu-luogo-{idx}")
        x["dal"] = st.text_input("Dal (AAAA-MM)", x["dal"], key=f"edu-dal-{idx}")
        x["al"] = st.text_input("Al (AAAA-MM)", x["al"], key=f"edu-al-{idx}")
        x["descrizione"] = st.text_area("Descrizione", x["descrizione"], key=f"edu-desc-{idx}")

    if _list_editor(st, d["istruzione"],
                    lambda: {"titolo": "", "istituto": "", "luogo": "", "dal": "", "al": "",
                             "descrizione": ""}, row, "edu"):
        st.rerun()


def _string_list(st, items, label, key):
    def row(idx, _val):
        items[idx] = st.text_input(label, items[idx], key=f"{key}-txt-{idx}")
    if _list_editor(st, items, lambda: "", row, key):
        st.rerun()


def _step_competenze(st, d):
    k = d["competenze"]
    st.subheader("Lingue")

    def lrow(idx, x):
        x["lingua"] = st.text_input("Lingua", x["lingua"], key=f"lng-l-{idx}")
        x["livello"] = st.selectbox("Livello (QCER)", QCER,
                                    index=QCER.index(x["livello"]) if x["livello"] in QCER else 3,
                                    key=f"lng-lv-{idx}")
    if _list_editor(st, k["lingue"], lambda: {"lingua": "", "livello": "B2"}, lrow, "lng"):
        st.rerun()
    st.subheader("Competenze digitali")
    _string_list(st, k["digitali"], "Voce", "dig")
    st.subheader("Competenze trasversali")
    _string_list(st, k["soft"], "Voce", "soft")
    k["patente"] = st.text_input("Patente di guida", k["patente"])


def _step_extra(st, d):
    st.subheader("Certificazioni")
    _string_list(st, d["extra"]["certificazioni"], "Certificazione", "cert")
    st.subheader("Pubblicazioni")
    _string_list(st, d["extra"]["pubblicazioni"], "Pubblicazione", "pub")
    d["extra"]["note"] = st.text_area("Note (una riga per paragrafo)", d["extra"]["note"])


def _step_privacy(st, d):
    keys = list(PRIVACY_OPTS)
    cur = d["privacy"]["tipo"] if d["privacy"]["tipo"] in keys else "standard-it"
    d["privacy"]["tipo"] = st.radio("Dicitura sul CV", keys, index=keys.index(cur),
                                    format_func=PRIVACY_OPTS.get)
    if d["privacy"]["tipo"] == "custom":
        d["privacy"]["testoCustom"] = st.text_area("Testo personalizzato", d["privacy"]["testoCustom"])
    if d["privacy"]["tipo"] == "nessuna":
        st.warning("Senza autorizzazione al trattamento dei dati molti selezionatori italiani "
                   "non possono considerare il CV.")
    d["privacy"]["dataFirma"] = st.checkbox("Aggiungi riga data e firma", d["privacy"]["dataFirma"])
    st.caption("I dati del CV restano in un database locale su questo PC e non vengono mai trasmessi.")


def _step_layout(st, d):
    keys = list(LAYOUTS)
    cur = d["layout"] if d["layout"] in keys else "europass"
    d["layout"] = st.selectbox("Layout", keys, index=keys.index(cur), format_func=LAYOUTS.get)
    d["lang"] = st.selectbox("Lingua del documento", ["it", "en"],
                             index=0 if d["lang"] != "en" else 1,
                             format_func=lambda v: "Italiano" if v == "it" else "English")
    d["accent"] = st.color_picker("Colore accento (layout Moderno)", d["accent"] or "#1a5fb4")
    warns = []
    if not d["personal"]["nome"].strip() and not d["personal"]["cognome"].strip():
        warns.append("Nome e cognome mancanti.")
    if not d["personal"]["email"].strip():
        warns.append("Email mancante.")
    if not d["esperienze"] and not d["istruzione"]:
        warns.append("Nessuna esperienza né formazione inserita.")
    for w in warns:
        st.warning(w)


def _step_profilo(st, d):
    d["profilo"] = st.text_area("Sommario professionale (una riga per paragrafo)", d["profilo"])


def main():
    import streamlit as st

    st.set_page_config(page_title="Curriculum Builder", page_icon="📄", layout="wide")
    con = storage.init_db()

    # --- selezione CV (multi-CV: uno per candidatura) ---
    cvs = storage.list_cvs(con)
    if "cv_id" not in st.session_state:
        if cvs:
            st.session_state.cv_id = cvs[0][0]
        else:
            st.session_state.cv_id = storage.save_cv(con, None, "Il mio CV", storage.defaults())
            cvs = storage.list_cvs(con)
        st.session_state.data = storage.load_cv(con, st.session_state.cv_id)

    with st.sidebar:
        st.title("📄 Curriculum Builder")
        ids = [c[0] for c in cvs] or [st.session_state.cv_id]
        names = {c[0]: c[1] for c in cvs}
        sel = st.selectbox("CV", ids, index=ids.index(st.session_state.cv_id)
                           if st.session_state.cv_id in ids else 0,
                           format_func=lambda i: names.get(i, "CV"))
        if sel != st.session_state.cv_id:
            st.session_state.cv_id = sel
            st.session_state.data = storage.load_cv(con, sel)
            st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("Nuovo CV"):
            st.session_state.cv_id = storage.save_cv(con, None, "Nuovo CV", storage.defaults())
            st.session_state.data = storage.load_cv(con, st.session_state.cv_id)
            st.rerun()
        if c2.button("Elimina CV"):
            st.session_state.confirm_delete = True
        if st.session_state.get("confirm_delete"):
            st.error("Eliminare definitivamente questo CV da questo PC?")
            d1, d2 = st.columns(2)
            if d1.button("Sì, elimina"):
                storage.delete_cv(con, st.session_state.cv_id)
                st.session_state.pop("cv_id")
                st.session_state.pop("confirm_delete")
                st.rerun()
            if d2.button("Annulla"):
                st.session_state.pop("confirm_delete")
                st.rerun()
        nuovo_nome = st.text_input("Nome di questo CV", names.get(st.session_state.cv_id, "Il mio CV"))
        step = st.radio("Passi", STEPS)
        st.caption("Zero cloud: tutto resta su questo PC.")

    data = st.session_state.data

    col_form, col_prev = st.columns([2, 3])
    with col_form:
        st.header(step)
        handlers = {STEPS[0]: _step_personali, STEPS[1]: _step_profilo, STEPS[2]: _step_esperienze,
                    STEPS[3]: _step_istruzione, STEPS[4]: _step_competenze, STEPS[5]: _step_extra,
                    STEPS[6]: _step_privacy, STEPS[7]: _step_layout}
        handlers[step](st, data)

    css = _css(data.get("layout") or "europass")

    with col_prev:
        blind = st.toggle("Versione anonimizzata (blind CV)",
                          help="Nasconde foto, data di nascita, nazionalità, indirizzo e contatti; "
                               "nome e cognome diventano iniziali. I dati originali non vengono toccati.")
        shown = anonymize.anonymize(data) if blind else data
        doc = render_cv.render_document(shown, css)
        e1, e2, e3 = st.columns(3)
        e1.download_button("⬇ Scarica CV (HTML)", doc,
                           file_name="curriculum-anonimo.html" if blind else "curriculum.html",
                           mime="text/html",
                           help="Aprilo nel browser e stampa in PDF (Ctrl+P, formato A4)")
        e2.download_button("⬇ Esporta JSON", storage.export_json(data), file_name="curriculum.json",
                           mime="application/json")
        up = e3.file_uploader("Importa JSON", type=["json"], label_visibility="collapsed")
        if up is not None and st.session_state.get("imported") != up.name:
            try:
                st.session_state.data = storage.import_json(up.getvalue().decode("utf-8"))
                st.session_state.imported = up.name
                st.rerun()
            except ValueError as e:
                st.error(f"File JSON non valido: {e}")
        # tab per formato: scegli il layout guardandolo e stampa da lì
        # (la barra nell'anteprima chiede Completo/Anonimo e scatena window.print)
        anon_data = anonymize.anonymize(data)
        for tab, lay in zip(st.tabs(list(LAYOUTS.values())), LAYOUTS):
            with tab:
                st.components.v1.html(
                    render_cv.render_print_preview({**data, "layout": lay},
                                                   {**anon_data, "layout": lay}, _css(lay)),
                    height=1100, scrolling=True)

    storage.save_cv(con, st.session_state.cv_id, nuovo_nome, data)


main()
