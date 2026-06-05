"""Parser Acea / Acea Energia — bollette luce/gas/acqua Roma e Lazio 2024-2026."""

from __future__ import annotations

import re

from .base import BaseBollettaParser, ParsedBolletta
from .enel import _to_float, _to_iso

_DATE = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"

_RX_POD = re.compile(r"POD\s*:?\s*(IT\d{3}E\d{8})", re.I)
_RX_PDR = re.compile(r"PDR\s*:?\s*(\d{10,14})", re.I)
_RX_CODICE_CLIENTE = re.compile(r"(?:codice\s+cliente|n\.?\s*cliente)\s*:?\s*([\dA-Z]{6,12})", re.I)
_RX_TOTALE = re.compile(
    r"(?:totale\s+(?:da\s+pagare|fattura|bolletta)|importo\s+(?:totale|complessivo))[\s:€]*([\d.,]+)",
    re.I,
)
_RX_SCADENZA = re.compile(
    rf"(?:scadenza|pagare\s+entro|entro\s+il)\s+({_DATE})",
    re.I,
)
_RX_PERIODO = re.compile(
    rf"(?:periodo|periodo\s+di\s+riferimento|dal)[\s:]+({_DATE})\s*(?:al|-)\s*({_DATE})",
    re.I,
)
_RX_IVA = re.compile(r"IVA[\s:€]*([\d.,]+)", re.I)
_RX_KWH = re.compile(r"([\d.,]+)\s*kWh\b", re.I)
_RX_MC_GAS = re.compile(r"([\d.,]+)\s*Smc\b", re.I)
_RX_MC_ACQUA = re.compile(r"([\d.,]+)\s*(?:m³|mc)\s+(?:erogati|consumati|consumo)", re.I)


class AceaParser(BaseBollettaParser):
    NAME = "acea"
    FORNITORE_DISPLAY = "Acea Energia"

    def match(self, text: str) -> bool:
        t = text.lower()
        if "acea ato2" in t or "acea ato 2" in t:
            return True
        if "acea energia" in t:
            return True
        return "acea" in t and ("luce" in t or "gas" in t or "acqua" in t or "bolletta" in t)

    def parse(self, text: str) -> ParsedBolletta:
        out = ParsedBolletta(
            fornitore=self.FORNITORE_DISPLAY,
            parser_usato=self.NAME,
            confidence=0.0,
        )
        score = 0

        m = _RX_POD.search(text)
        if m:
            out.pod = m.group(1).upper()
            score += 2

        m = _RX_PDR.search(text)
        if m:
            out.pdr = m.group(1)
            score += 2

        m = _RX_CODICE_CLIENTE.search(text)
        if m:
            out.codice_cliente = m.group(1)
            score += 1

        m = _RX_TOTALE.search(text)
        if m:
            out.importo_totale = _to_float(m.group(1))
            score += 2

        m = _RX_IVA.search(text)
        if m:
            out.iva = _to_float(m.group(1))
            score += 1

        m = _RX_SCADENZA.search(text)
        if m:
            try:
                out.scadenza = _to_iso(m.group(1))
                score += 2
            except (ValueError, IndexError):
                pass

        m = _RX_PERIODO.search(text)
        if m:
            try:
                out.periodo_inizio = _to_iso(m.group(1))
                out.periodo_fine = _to_iso(m.group(2))
                score += 2
            except (ValueError, IndexError):
                pass

        m_kwh = _RX_KWH.search(text)
        if m_kwh:
            out.consumo_qta = _to_float(m_kwh.group(1))
            out.consumo_unita = "kWh"
            out.tipo = "luce"
            score += 1
        elif _RX_MC_GAS.search(text):
            m_gas = _RX_MC_GAS.search(text)
            out.consumo_qta = _to_float(m_gas.group(1))
            out.consumo_unita = "Smc"
            out.tipo = "gas"
            score += 1
        elif _RX_MC_ACQUA.search(text):
            m_acqua = _RX_MC_ACQUA.search(text)
            out.consumo_qta = _to_float(m_acqua.group(1))
            out.consumo_unita = "mc"
            out.tipo = "acqua"
            score += 1

        out.confidence = min(1.0, score / 11.0)
        return out
