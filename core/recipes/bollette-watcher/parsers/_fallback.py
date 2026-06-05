"""Parser fallback euristico — usato se nessun vendor matcha.

Tenta di estrarre l'essenziale (importo totale + scadenza + tipo intuito
da kWh/Smc/GB presenti) con regex generiche. Confidence ≤ 0.5.
"""

from __future__ import annotations

import re
from .base import BaseBollettaParser, ParsedBolletta
from .enel import _to_iso, _to_float

_RX_EURO    = re.compile(r"(?:€|EUR)\s*([0-9.]+,[0-9]{2})", re.I)
_RX_TOTALE  = re.compile(r"totale[^\n]{0,30}?([0-9.]+,[0-9]{2})", re.I)
_RX_SCADENZ = re.compile(r"scaden[^\n]{0,20}?([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})", re.I)
_RX_KWH     = re.compile(r"([0-9.]+)\s*kWh\b", re.I)
_RX_MC      = re.compile(r"([0-9.]+)\s*(?:Smc|mc)\b", re.I)
_RX_GB      = re.compile(r"([0-9.,]+)\s*GB\b", re.I)


class FallbackParser(BaseBollettaParser):
    NAME = "_fallback"
    FORNITORE_DISPLAY = "Sconosciuto (parser euristico)"

    def match(self, text: str) -> bool:
        return True

    def parse(self, text: str) -> ParsedBolletta:
        out = ParsedBolletta(
            fornitore=self.FORNITORE_DISPLAY,
            parser_usato=self.NAME,
            raw_text=text[:5000],
        )

        if (m := _RX_TOTALE.search(text)):
            out.importo_totale = _to_float(m.group(1))
        elif (m := _RX_EURO.search(text)):
            out.importo_totale = _to_float(m.group(1))

        if (m := _RX_SCADENZ.search(text)):
            out.scadenza = _to_iso(m.group(1))

        if _RX_KWH.search(text):
            out.tipo = "luce"
            out.consumo_unita = "kWh"
        elif _RX_MC.search(text):
            out.tipo = "gas"
            out.consumo_unita = "Smc"
        elif _RX_GB.search(text):
            out.tipo = "internet"
            out.consumo_unita = "GB"

        filled = sum(1 for v in [out.tipo, out.importo_totale, out.scadenza] if v)
        out.confidence = min(0.5, filled / 3.0 * 0.5)
        return out
