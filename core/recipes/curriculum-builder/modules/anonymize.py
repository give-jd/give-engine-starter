"""Blind CV: versione anonimizzata con set di mascheratura standard fisso.

Funzione pura: deep-copy, l'originale non viene mai toccato.
Maschera: foto, data di nascita, nazionalità, indirizzo, email, telefono, LinkedIn, sito.
Nome e cognome -> iniziali ("M. B."). Restano: contenuti, aziende, istituti, dicitura privacy.
"""

from copy import deepcopy

_CLEARED = ("email", "tel", "indirizzo", "dataNascita", "nazionalita", "linkedin", "sito")


def _initial(s: str) -> str:
    s = str(s or "").strip()
    return f"{s[0].upper()}." if s else ""


def anonymize(cv: dict) -> dict:
    a = deepcopy(cv)
    p = a.get("personal", {})
    p["nome"] = _initial(p.get("nome"))
    p["cognome"] = _initial(p.get("cognome"))
    p["foto"] = None
    for k in _CLEARED:
        p[k] = ""
    return a
