"""Parser Vodafone — bollette Vodafone Italia formato standard 2024-2026."""

from __future__ import annotations

import re
from .base import BaseBollettaParser, ParsedBolletta

_RX_POD = re.compile(r"POD\s*:?\s*([A-Z0-9]{14,20})", re.I)
_RX_PDR = re.compile(r"PDR\s*:?\s*([0-9]{10,14})", re.I)
_RX_TOTALE = re.compile(
    r"(?:Totale\s+(?:da\s+pagare|bolletta|fattura)|importo\s+totale)[\s:€]*([0-9.,]+)",
    re.I,
)
_RX_SCADENZA = re.compile(
    r"(?:scaden\w*\s+il|entro\s+il|pagare\s+entro|scadenza)\s+([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
    re.I,
)
_RX_PERIODO = re.compile(
    r"(?:periodo|consumo\s+dal|periodo\s+di\s+riferimento)\s*[:]?\s*([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})\s*(?:al|-)\s*([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
    re.I,
)
_RX_KWH = re.compile(r"([0-9.,]+)\s*kWh\b", re.I)
_RX_MC = re.compile(r"([0-9.,]+)\s*(?:Smc|mc|metri\s+cubi)\b", re.I)
_RX_IVA = re.compile(r"IVA\s*[€:]*\s*([0-9.,]+)", re.I)


def _to_iso(date_it: str) -> str:
    s = re.sub(r"[/.-]", "/", date_it.strip())
    parts = s.split("/")
    if len(parts) != 3:
        return date_it
    d, m, y = parts
    if len(y) == 2:
        y = "20" + y
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except ValueError:
        return date_it


def _to_float(s):
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


_MATCH_TERMS = ['vodafone italia', 'vodafone.it', 'vodafone red']


class VodafoneParser(BaseBollettaParser):
    NAME = "vodafone"
    FORNITORE_DISPLAY = "Vodafone Italia"
    TIPO = "telefonia"

    def match(self, text: str) -> bool:
        low = text.lower()
        return any(t in low for t in _MATCH_TERMS)

    def parse(self, text: str) -> ParsedBolletta:
        result = ParsedBolletta(
            fornitore=self.FORNITORE_DISPLAY,
            tipo=self.TIPO,
            parser_usato=self.NAME,
        )
        m = _RX_POD.search(text)
        if m:
            result.pod_pdr = m.group(1)
        elif (m := _RX_PDR.search(text)):
            result.pod_pdr = m.group(1)

        if (m := _RX_TOTALE.search(text)):
            result.importo_totale = _to_float(m.group(1))
        if (m := _RX_IVA.search(text)):
            result.iva = _to_float(m.group(1))
        if (m := _RX_SCADENZA.search(text)):
            result.scadenza = _to_iso(m.group(1))
        if (m := _RX_PERIODO.search(text)):
            result.periodo_inizio = _to_iso(m.group(1))
            result.periodo_fine = _to_iso(m.group(2))

        if (m := _RX_KWH.search(text)):
            result.consumo_qta = _to_float(m.group(1))
            result.consumo_unita = "kWh"
            if not result.tipo or result.tipo == "telefonia":
                result.tipo = "luce"
        elif (m := _RX_MC.search(text)):
            result.consumo_qta = _to_float(m.group(1))
            result.consumo_unita = "Smc"
            result.tipo = "gas"

        filled = sum(1 for v in (result.pod_pdr, result.importo_totale,
                                  result.scadenza, result.periodo_inizio,
                                  result.consumo_qta, result.fornitore) if v)
        result.confidence = filled / 6.0
        return result
