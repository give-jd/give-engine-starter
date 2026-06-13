"""Etichette IT/EN, diciture trattamento dati, formati data.

Porting 1:1 dal prototipo validato (uni-code/js/i18n.js).
"""

LABELS = {
    "it": {
        "profilo": "Profilo", "esperienze": "Esperienza lavorativa",
        "istruzione": "Istruzione e formazione", "competenze": "Competenze",
        "lingue": "Competenze linguistiche", "digitali": "Competenze digitali",
        "soft": "Competenze trasversali", "patente": "Patente di guida",
        "certificazioni": "Certificazioni", "pubblicazioni": "Pubblicazioni",
        "note": "Note", "privacy": "Trattamento dei dati",
        "email": "Email", "tel": "Telefono", "indirizzo": "Indirizzo",
        "dataNascita": "Data di nascita", "nazionalita": "Nazionalità",
        "linkedin": "LinkedIn", "sito": "Sito web",
        "presente": "presente", "data": "Data", "firma": "Firma",
        "comprensione": "Comprensione", "parlato": "Parlato", "scritto": "Scritto",
    },
    "en": {
        "profilo": "Profile", "esperienze": "Work experience",
        "istruzione": "Education and training", "competenze": "Skills",
        "lingue": "Language skills", "digitali": "Digital skills",
        "soft": "Soft skills", "patente": "Driving licence",
        "certificazioni": "Certifications", "pubblicazioni": "Publications",
        "note": "Notes", "privacy": "Data processing consent",
        "email": "Email", "tel": "Phone", "indirizzo": "Address",
        "dataNascita": "Date of birth", "nazionalita": "Nationality",
        "linkedin": "LinkedIn", "sito": "Website",
        "presente": "present", "data": "Date", "firma": "Signature",
        "comprensione": "Understanding", "parlato": "Speaking", "scritto": "Writing",
    },
}

PRIVACY_TEXTS = {
    "standard-it": ("Autorizzo il trattamento dei miei dati personali ai sensi del "
                    "Regolamento (UE) 2016/679 (GDPR) e del D.Lgs. 196/2003 e ss.mm.ii."),
    "standard-en": ("I hereby authorize the processing of my personal data pursuant to "
                    "Regulation (EU) 2016/679 (GDPR) and Italian Legislative Decree 196/2003, as amended."),
}


def t(key: str, lang: str) -> str:
    return LABELS.get(lang, LABELS["it"]).get(key) or LABELS["it"].get(key, key)


def fmt_date(iso: str) -> str:
    """'YYYY-MM' -> 'MM/YYYY'; 'YYYY-MM-DD' -> 'DD/MM/YYYY'; '' -> ''."""
    if not iso:
        return ""
    p = str(iso).split("-")
    if len(p) == 3:
        return f"{p[2]}/{p[1]}/{p[0]}"
    if len(p) == 2:
        return f"{p[1]}/{p[0]}"
    return str(iso)


def fmt_period(dal: str, al: str, corrente: bool, lang: str) -> str:
    a = fmt_date(dal)
    b = t("presente", lang) if corrente else fmt_date(al)
    return " – ".join(x for x in (a, b) if x)
