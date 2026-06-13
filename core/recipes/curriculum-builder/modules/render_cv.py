"""Dati CV -> documento HTML. Porting 1:1 dal prototipo (uni-code/js/render.js): stesso DOM, stesse classi.

Regola assoluta: OGNI testo utente passa da esc(). I 4 layout CSS del prototipo
si applicano invariati al wrapper `.cv--<layout>`.
"""

from html import escape

from . import i18n


def esc(s) -> str:
    return escape(str(s if s is not None else ""), quote=True)


def _paragraphs(text) -> str:
    rows = [r.strip() for r in str(text or "").split("\n") if r.strip()]
    return "".join(f'<p class="cv-text">{esc(r)}</p>' for r in rows)


def _section(key: str, lang: str, sec: str, inner: str) -> str:
    title = esc(i18n.t(key, lang))
    return (f'<section class="cv-section" data-sec="{sec}">'
            f'<h2 class="cv-section-title">{title}</h2>{inner}</section>')


def _simple_list(items) -> str:
    vals = [str(v).strip() for v in (items or []) if str(v).strip()]
    if not vals:
        return ""
    lis = "".join(f"<li>{esc(v)}</li>" for v in vals)
    return f'<ul class="cv-list">{lis}</ul>'


def _items_section(key, lang, sec, items, role_field, org_fields, has_corrente):
    parts = []
    for x in items:
        org = esc(", ".join(str(x.get(f, "")) for f in org_fields if x.get(f)))
        period = esc(i18n.fmt_period(x.get("dal", ""), x.get("al", ""),
                                     bool(x.get("corrente")) if has_corrente else False, lang))
        body = _paragraphs(x.get("descrizione", "")) if x.get("descrizione") else ""
        parts.append(
            f'<article class="cv-item"><div class="cv-item-head">'
            f'<strong class="cv-item-role">{esc(x.get(role_field, ""))}</strong>'
            f'<span class="cv-item-org">{org}</span></div>'
            f'<div class="cv-item-period">{period}</div>{body}</article>')
    return _section(key, lang, sec, "".join(parts))


def render_body(d: dict) -> str:
    lang = d.get("lang") or "it"
    p = d.get("personal", {})

    # ---- header ----
    photo = f'<img class="cv-photo" alt="" src="{esc(p.get("foto"))}">' if p.get("foto") else ""
    name = esc(f'{p.get("nome", "")} {p.get("cognome", "")}'.strip())
    contact_rows = []
    for key, val in (("email", p.get("email")), ("tel", p.get("tel")), ("indirizzo", p.get("indirizzo")),
                     ("dataNascita", i18n.fmt_date(p.get("dataNascita", ""))),
                     ("nazionalita", p.get("nazionalita")), ("linkedin", p.get("linkedin")),
                     ("sito", p.get("sito"))):
        if val:
            contact_rows.append(f'<div class="cv-contact"><span class="cv-contact-label">{esc(i18n.t(key, lang))}'
                                f'</span><span class="cv-contact-value">{esc(val)}</span></div>')
    header = (f'<header class="cv-header">{photo}<h1 class="cv-name">{name}</h1>'
              f'<div class="cv-contacts">{"".join(contact_rows)}</div></header>')

    # ---- side: lingue (doppia forma), digitali, soft, patente ----
    side_parts = []
    comp = d.get("competenze", {})
    lingue = comp.get("lingue", [])
    if lingue:
        compact = "".join(f'<li>{esc(l.get("lingua", ""))} — {esc(l.get("livello", ""))}</li>' for l in lingue)
        head = "".join(f"<th>{esc(i18n.t(h, lang)) if h else ''}</th>" for h in ("", "comprensione", "parlato", "scritto"))
        rows = "".join(
            f'<tr><td class="cv-lang-name">{esc(l.get("lingua", ""))}</td>'
            + f'<td class="cv-lang-level">{esc(l.get("livello", ""))}</td>' * 3 + "</tr>"
            for l in lingue)
        inner = (f'<ul class="cv-lang-compact">{compact}</ul>'
                 f'<table class="cv-lang-grid"><tr>{head}</tr>{rows}</table>')
        side_parts.append(_section("lingue", lang, "lingue", inner))
    for key, sec in (("digitali", "digitali"), ("soft", "soft")):
        lst = _simple_list(comp.get(key))
        if lst:
            side_parts.append(_section(key, lang, sec, lst))
    if str(comp.get("patente", "")).strip():
        side_parts.append(_section("patente", lang, "patente", f'<p class="cv-text">{esc(comp["patente"])}</p>'))

    # ---- main: profilo, esperienze, istruzione, certificazioni, pubblicazioni, note ----
    main_parts = []
    if str(d.get("profilo", "")).strip():
        main_parts.append(_section("profilo", lang, "profilo", _paragraphs(d["profilo"])))
    if d.get("esperienze"):
        main_parts.append(_items_section("esperienze", lang, "esperienze",
                                         d["esperienze"], "ruolo", ("azienda", "luogo"), True))
    if d.get("istruzione"):
        main_parts.append(_items_section("istruzione", lang, "istruzione",
                                         d["istruzione"], "titolo", ("istituto", "luogo"), False))
    extra = d.get("extra", {})
    for key, sec in (("certificazioni", "certificazioni"), ("pubblicazioni", "pubblicazioni")):
        lst = _simple_list(extra.get(key))
        if lst:
            main_parts.append(_section(key, lang, sec, lst))
    if str(extra.get("note", "")).strip():
        main_parts.append(_section("note", lang, "note", _paragraphs(extra["note"])))

    # ---- privacy: figlia diretta del wrapper, sempre in coda ----
    privacy = ""
    ptipo = d.get("privacy", {}).get("tipo", "standard-it")
    if ptipo != "nessuna":
        text = d["privacy"].get("testoCustom", "") if ptipo == "custom" else i18n.PRIVACY_TEXTS.get(ptipo, "")
        if text:
            sign = ""
            if d["privacy"].get("dataFirma"):
                sign = (f'<div class="cv-sign-row"><span>{esc(i18n.t("data", lang))}: ____________</span>'
                        f'<span>{esc(i18n.t("firma", lang))}: ____________________</span></div>')
            privacy = (f'<div class="cv-section cv-privacy" data-sec="privacy">'
                       f'<p class="cv-privacy-text">{esc(text)}</p>{sign}</div>')

    return (header
            + f'<div class="cv-side">{"".join(side_parts)}</div>'
            + f'<div class="cv-main">{"".join(main_parts)}</div>'
            + privacy)


_TOOLBAR_CSS = """
.print-toolbar { position: sticky; top: 0; background: #1f2933; color: #f9fafb;
  padding: 8px 14px; font-family: system-ui, sans-serif; font-size: 14px; z-index: 10; }
.print-toolbar button { font: inherit; padding: 4px 12px; margin-right: 6px;
  border: 1px solid #4b5563; border-radius: 4px; background: #374151; color: #f9fafb; cursor: pointer; }
.print-toolbar button:hover { background: #4b5563; }
.hide { display: none !important; }
@media print { .no-print { display: none !important; } }
"""


def render_print_preview(cv: dict, cv_anon: dict, css: str) -> str:
    """Anteprima interattiva: barra stampa (scelta Completo/Anonimo) + entrambe le varianti.

    Il toggle di visibilità usa classList, non style.display: i layout a grid
    (Moderno, Compatto) devono riavere il loro display CSS dopo la stampa.
    """
    lang = cv.get("lang") or "it"
    layout = cv.get("layout") or "europass"
    accent = esc(cv.get("accent") or "#1a5fb4")
    return (
        f'<!DOCTYPE html>\n<html lang="{esc(lang)}"><head><meta charset="utf-8">'
        f"<title>Anteprima CV</title><style>{css}{_TOOLBAR_CSS}</style></head><body>"
        '<div class="no-print print-toolbar">'
        '<button id="btn-print" onclick="document.getElementById(\'print-choice\').classList.remove(\'hide\')">'
        "\U0001f5b6 Stampa</button>"
        '<span id="print-choice" class="hide">'
        "<button onclick=\"stampa('full')\">Completo</button>"
        "<button onclick=\"stampa('anon')\">Anonimo</button>"
        '<button onclick="chiudi()">Annulla</button></span></div>'
        f'<div id="cv-full" class="cv-sheet cv--{esc(layout)}" style="--accent: {accent}">{render_body(cv)}</div>'
        f'<div id="cv-anon" class="cv-sheet cv--{esc(layout)} hide" style="--accent: {accent}">{render_body(cv_anon)}</div>'
        "<script>\n"
        "function stampa(mode) {\n"
        "  document.getElementById('cv-full').classList.toggle('hide', mode !== 'full');\n"
        "  document.getElementById('cv-anon').classList.toggle('hide', mode !== 'anon');\n"
        "  window.print();\n"
        "  document.getElementById('cv-full').classList.remove('hide');\n"
        "  document.getElementById('cv-anon').classList.add('hide');\n"
        "  chiudi();\n"
        "}\n"
        "function chiudi() { document.getElementById('print-choice').classList.add('hide'); }\n"
        "</script></body></html>")


def render_document(cv: dict, css: str) -> str:
    lang = cv.get("lang") or "it"
    layout = cv.get("layout") or "europass"
    accent = cv.get("accent") or "#1a5fb4"
    p = cv.get("personal", {})
    title = esc(f'CV {p.get("nome", "")} {p.get("cognome", "")}'.strip())
    return (f'<!DOCTYPE html>\n<html lang="{esc(lang)}"><head><meta charset="utf-8">'
            f"<title>{title}</title><style>{css}</style></head>"
            f'<body><div id="cv-preview" class="cv--{esc(layout)}" style="--accent: {esc(accent)}">'
            f"{render_body(cv)}</div></body></html>")
