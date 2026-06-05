"""Parser Enel Energia — bollette luce/gas formato standard 2024-2026."""

from __future__ import annotations

import re
from .base import BaseBollettaParser, ParsedBolletta

_RX_POD      = re.compile(r"POD\s*:?\s*([A-Z0-9]{14,20})", re.I)
_RX_PDR      = re.compile(r"PDR\s*:?\s*([0-9]{10,14})", re.I)
_RX_TOTALE = re.compile(
    r"(?:Totale\s+(?:da\s+pagare|bolletta|fattura)|importo\s+totale)[\s:€]*([0-9.,]+)",
    re.I,
)
_RX_SCADENZA = re.compile(
    r"(?:scaden\w*\s+il|entro\s+il|pagare\s+entro|scadenza)\s+([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
    re.I,
)
_RX_PERIODO  = re.compile(
    r"(?:periodo|consumo dal)[\s:]+([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})\s*(?:al|-)\s*([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
    re.I,
)
_RX_IVA = re.compile(r"IVA[\s:€]*([0-9.,]+)", re.I)
_RX_KWH = re.compile(r"([0-9.,]+)\s*kWh\b", re.I)
_RX_MC  = re.compile(r"([0-9.,]+)\s*(?:Smc|mc|metri cubi)\b", re.I)


def _to_iso(date_it: str) -> str:
    s = re.sub(r"[/.-]", "/", date_it.strip())
    parts = s.split("/")
    if len(parts) != 3:
        return date_it
    d, m, y = parts
    if len(y) == 2:
        y = "20" + y
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _to_float(s: str) -> float:
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


class EnelParser(BaseBollettaParser):
    NAME = "enel"
    FORNITORE_DISPLAY = "Enel Energia"

    def match(self, text: str) -> bool:
        t = text.lower()
        return "enel" in t and ("energia" in t or "servizio elettrico" in t)

    def parse(self, text: str) -> ParsedBolletta:
        out = ParsedBolletta(
            fornitore=self.FORNITORE_DISPLAY,
            parser_usato=self.NAME,
            raw_text=text[:5000],
        )

        if _RX_POD.search(text):
            out.pod_pdr = _RX_POD.search(text).group(1).upper()
            out.tipo = "luce"
        elif _RX_PDR.search(text):
            out.pod_pdr = _RX_PDR.search(text).group(1)
            out.tipo = "gas"

        if (m := _RX_TOTALE.search(text)):
            out.importo_totale = _to_float(m.group(1))

        if (m := _RX_SCADENZA.search(text)):
            out.scadenza = _to_iso(m.group(1))

        if (m := _RX_PERIODO.search(text)):
            out.periodo_inizio = _to_iso(m.group(1))
            out.periodo_fine = _to_iso(m.group(2))

        if out.tipo == "luce":
            kwh = _RX_KWH.findall(text)
            if kwh:
                vals = [_to_float(x) for x in kwh[:3]]
                out.consumo_qta = sum(vals) / max(1, len(vals))
                out.consumo_unita = "kWh"
        elif out.tipo == "gas":
            mc = _RX_MC.findall(text)
            if mc:
                vals = [_to_float(x) for x in mc[:3]]
                out.consumo_qta = sum(vals) / max(1, len(vals))
                out.consumo_unita = "Smc"

        filled = sum(1 for v in [out.tipo, out.pod_pdr, out.importo_totale,
                                  out.scadenza, out.consumo_qta] if v)
        out.confidence = min(1.0, filled / 5.0)
        return out
