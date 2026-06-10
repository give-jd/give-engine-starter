"""Preset parametrici per il calendario rifiuti comunale.

ATTENZIONE — dati parametrici, NON verita' assoluta. Frazioni, colori e soprattutto
la mappa materiale->frazione *variano per comune*. Questi preset servono solo come
punto di partenza: l'utente deve sempre verificare il regolamento del PROPRIO comune.
"""

from __future__ import annotations

DISCLAIMER: str = (
    "Questi sono valori di partenza generici: la suddivisione in frazioni e il "
    "'dove butto X' VARIANO da comune a comune. Verifica sempre il regolamento "
    "del tuo comune prima di affidarti a questi suggerimenti."
)


# Preset frazioni standard italiane: nome -> (colore esadecimale indicativo, icona).
# Il colore e' indicativo (i bidoni reali variano per gestore/comune).
FRAZIONI_PRESET: list[dict[str, str]] = [
    {"nome": "Umido", "colore": "#6B4423", "icona": "apple"},
    {"nome": "Indifferenziato", "colore": "#4A4A4A", "icona": "trash-2"},
    {"nome": "Carta e cartone", "colore": "#1E6FB8", "icona": "newspaper"},
    {"nome": "Plastica e lattine", "colore": "#F2C200", "icona": "recycle"},
    {"nome": "Vetro", "colore": "#2E8B57", "icona": "wine"},
    {"nome": "Verde e sfalci", "colore": "#3B7A1E", "icona": "leaf"},
    {"nome": "RAEE", "colore": "#8E44AD", "icona": "plug"},
    {"nome": "Ingombranti", "colore": "#A0522D", "icona": "sofa"},
    {"nome": "Farmaci", "colore": "#C0392B", "icona": "pill"},
    {"nome": "Pile e batterie", "colore": "#D35400", "icona": "battery"},
]


# Regolamento default materiale -> nome frazione. DATO PARAMETRICO CON DISCLAIMER.
# Sempre presentato come suggerimento, mai come regola del comune dell'utente.
REGOLAMENTO_DEFAULT: list[dict[str, str]] = [
    {"materiale": "avanzi di cibo", "frazione": "Umido"},
    {"materiale": "bucce di frutta e verdura", "frazione": "Umido"},
    {"materiale": "fondi di caffe'", "frazione": "Umido"},
    {"materiale": "tovaglioli di carta sporchi", "frazione": "Umido"},
    {"materiale": "pannolini e pannoloni", "frazione": "Indifferenziato"},
    {"materiale": "cocci di ceramica", "frazione": "Indifferenziato"},
    {"materiale": "giocattoli rotti", "frazione": "Indifferenziato"},
    {"materiale": "scontrini", "frazione": "Indifferenziato"},
    {"materiale": "giornali e riviste", "frazione": "Carta e cartone"},
    {"materiale": "scatole di cartone", "frazione": "Carta e cartone"},
    {"materiale": "quaderni", "frazione": "Carta e cartone"},
    {"materiale": "bottiglie di plastica", "frazione": "Plastica e lattine"},
    {"materiale": "lattine", "frazione": "Plastica e lattine"},
    {"materiale": "flaconi di detersivo", "frazione": "Plastica e lattine"},
    {"materiale": "vasetti di vetro", "frazione": "Vetro"},
    {"materiale": "bottiglie di vetro", "frazione": "Vetro"},
    {"materiale": "sfalci d'erba", "frazione": "Verde e sfalci"},
    {"materiale": "potature", "frazione": "Verde e sfalci"},
    {"materiale": "foglie secche", "frazione": "Verde e sfalci"},
    {"materiale": "elettrodomestici", "frazione": "RAEE"},
    {"materiale": "telefoni e tablet", "frazione": "RAEE"},
    {"materiale": "lampadine a basso consumo", "frazione": "RAEE"},
    {"materiale": "mobili", "frazione": "Ingombranti"},
    {"materiale": "materassi", "frazione": "Ingombranti"},
    {"materiale": "farmaci scaduti", "frazione": "Farmaci"},
    {"materiale": "pile stilo", "frazione": "Pile e batterie"},
    {"materiale": "batterie", "frazione": "Pile e batterie"},
]


def frazione_preset(nome: str) -> dict[str, str] | None:
    """Restituisce il preset (colore/icona) per il nome frazione, se esiste.

    Args:
        nome: Nome della frazione (case-insensitive).

    Returns:
        Il dict del preset, oppure ``None`` se non riconosciuta.
    """
    nome_l = nome.strip().lower()
    for p in FRAZIONI_PRESET:
        if p["nome"].lower() == nome_l:
            return p
    return None
