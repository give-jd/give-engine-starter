"""Parser Edison Energia — bollette luce/gas formato 2024-2026."""

from __future__ import annotations

import re

from .base import BaseBollettaParser, ParsedBolletta
from .enel import _to_float, _to_iso

_RX_POD = re.compile(r"POD\s*:?\s*([A-Z0-9]{14,20})", re.I)
_RX_PDR = re.compile(r"PDR\s*:?\s*(\d{10,14})", re.I)
_RX_TOTALE = re.compile(
    r"(?:totale\s+(?:da\s+pagare|fattura|bolletta)|importo\s+totale)[\s:€]*([\d.,]+)",
    re.I,
)
_RX_SCADENZA = re.compile(
    r"(?:scaden\w*\s+il|entro\s+il|pagare\s+entro|scadenza)\s+(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
    re.I,
)
_RX_PERIODO = re.compile(
    r"(?:periodo|periodo dal|periodo di consumo)[\s:]+(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s*(?:al|-)\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
    re.I,
)
_RX_IVA = re.compile(r"IVA[\s:€]*([\d.,]+)", re.I)
_RX_KWH = re.compile(r"([\d.,]+)\s*kWh\b", re.I)
_RX_MC = re.compile(r"([\d.,]+)\s*(?:Smc|mc|metri cubi)\b", re.I)


class EdisonParser(BaseBollettaParser):
    NAME = "edison"
    FORNITORE_DISPLAY = "Edison Energia"

    def match(self, text: str) -> bool:
        t = text.lower()
        return "edison" in t and (
            "energia" in t or "luce" in t or "gas" in t or "bolletta" in t
        )

    def parse(self, text: str) -> ParsedBolletta:
        out = ParsedBolletta(
            fornitore=self.FORNITORE_DISPLAY,
            parser_usato=self.NAME,
            raw_text=text[:5000],
        )

        if m := _RX_POD.search(text):
            out.pod_pdr = m.group(1).upper()
            out.tipo = "luce"
        elif m := _RX_PDR.search(text):
            out.pod_pdr = m.group(1)
            out.tipo = "gas"

        if m := _RX_TOTALE.search(text):
            out.importo_totale = _to_float(m.group(1))

        if m := _RX_SCADENZA.search(text):
            out.scadenza = _to_iso(m.group(1))

        if m := _RX_PERIODO.search(text):
            out.periodo_inizio = _to_iso(m.group(1))
            out.periodo_fine = _to_iso(m.group(2))

        if m := _RX_IVA.search(text):
            out.iva = _to_float(m.group(1))

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

        filled = sum(
            1
            for v in [
                out.tipo,
                out.pod_pdr,
                out.importo_totale,
                out.scadenza,
                out.consumo_qta,
            ]
            if v
        )
        out.confidence = min(1.0, filled / 5.0)
        return out
