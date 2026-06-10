"""Adapter di esempio: calendario settimanale in formato testuale semplice.

Riconosce blocchi del tipo::

    Umido: lunedi, giovedi
    Plastica e lattine: mercoledi
    Carta e cartone: martedi

Una riga per frazione, con i giorni della settimana in italiano. E' un esempio
realistico ma volutamente semplice: serve da modello per adapter per-comune.
"""

from __future__ import annotations

import re

from .base import BaseCalendarParser, ParsedCalendar, RicorrenzaParsed

# mappa giorno italiano (normalizzato senza accenti) -> ISO weekday (1=lun .. 7=dom)
_GIORNI = {
    "lunedi": 1, "lun": 1,
    "martedi": 2, "mar": 2,
    "mercoledi": 3, "mer": 3,
    "giovedi": 4, "gio": 4,
    "venerdi": 5, "ven": 5,
    "sabato": 6, "sab": 6,
    "domenica": 7, "dom": 7,
}

_RX_RIGA = re.compile(r"^\s*([A-Za-zÀ-ÿ &']+?)\s*[:\-]\s*(.+?)\s*$")


def _normalizza(s: str) -> str:
    return (
        s.lower()
        .replace("à", "a").replace("è", "e").replace("é", "e")
        .replace("ì", "i").replace("í", "i")
        .replace("ò", "o").replace("ù", "u").replace("'", "")
        .strip()
    )


class EsempioSettimanaleParser(BaseCalendarParser):
    """Parser per calendari settimanali testuali 'Frazione: giorni'."""

    NAME = "esempio_settimanale"
    COMUNE_DISPLAY = None

    def _estrai_giorni(self, parte: str) -> list[int]:
        out: list[int] = []
        for token in re.split(r"[,/]|\be\b|\s+", parte):
            t = _normalizza(token)
            if t in _GIORNI:
                iso = _GIORNI[t]
                if iso not in out:
                    out.append(iso)
        return sorted(out)

    def match(self, text: str) -> bool:
        righe_valide = 0
        for riga in text.splitlines():
            m = _RX_RIGA.match(riga)
            if not m:
                continue
            if self._estrai_giorni(m.group(2)):
                righe_valide += 1
        return righe_valide >= 2

    def parse(self, text: str) -> ParsedCalendar:
        cal = ParsedCalendar(parser_usato=self.NAME, raw_text=text)
        n_match = 0
        for riga in text.splitlines():
            m = _RX_RIGA.match(riga)
            if not m:
                continue
            frazione = m.group(1).strip()
            giorni = self._estrai_giorni(m.group(2))
            if not giorni:
                continue
            cal.ricorrenze.append(
                RicorrenzaParsed(
                    frazione=frazione,
                    tipo="settimanale",
                    giorni_settimana=",".join(str(g) for g in giorni),
                )
            )
            n_match += 1
        cal.confidence = min(1.0, n_match / 4.0) if n_match else 0.0
        return cal
