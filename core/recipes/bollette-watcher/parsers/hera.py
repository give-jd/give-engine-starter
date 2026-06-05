"""Parser Hera Comm — bollette luce/gas/acqua nord-est Italia 2024-2026."""

from __future__ import annotations

import re

from .base import BaseBollettaParser, ParsedBolletta
from .enel import _to_float, _to_iso

_DATE = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"

_RX_POD = re.compile(r"POD\s*:?\s*(IT\d{3}E\d{8})", re.I)
_RX_PDR = re.compile(r"(?:PDR|punto\s+di\s+riconsegna)\s*:?\s*(\d{10,14})", re.I)
_RX_CODICE_UTENTE = re.compile(r"(?:codice\s+(?:utente|cliente)|matricola)\s*:?\s*(\d{7,12})", re.I)
_RX_TOTALE = re.compile(
    r"(?:totale\s+(?:da\s+pagare|bolletta|fattura)|importo\s+(?:totale|dovuto))[\s:€]*([\d.,]+)",
    re.I,
)
_RX_SCADENZA = re.compile(
    rf"(?:da\s+pagare\s+entro|scaden\w*\s+(?:il|al)|entro\s+il)\s+({_DATE})",
    re.I,
)
_RX_PERIODO = re.compile(
    rf"(?:periodo\s+di\s+riferimento|periodo)[\s:]+(?:dal\s+)?({_DATE})\s*(?:al|-)\s*({_DATE})",
    re.I,
)
_RX_IVA = re.compile(r"IVA[\s:€%]*([\d.,]+)", re.I)
_RX_KWH = re.compile(r"([\d.,]+)\s*kWh\b", re.I)
_RX_MC = re.compile(r"([\d.,]+)\s*(?:Smc|mc)\b", re.I)
_RX_LITRI = re.compile(r"([\d.,]+)\s*(?:m³|metri cubi|mc)\b\s+(?:acqua|consumo idrico)", re.I)


def _extract_consumo(text: str, out: ParsedBolletta) -> int:
    """Rileva consumo luce/acqua/gas (priorità kWh > acqua > Smc). Ritorna score."""
    m_kwh = _RX_KWH.search(text)
    if m_kwh:
        out.consumo_qta = _to_float(m_kwh.group(1))
        out.consumo_unita = "kWh"
        out.tipo = "luce"
        return 1
    m_acqua = _RX_LITRI.search(text)
    if m_acqua:
        out.consumo_qta = _to_float(m_acqua.group(1))
        out.consumo_unita = "mc"
        out.tipo = "acqua"
        return 1
    m_mc = _RX_MC.search(text)
    if m_mc:
        out.consumo_qta = _to_float(m_mc.group(1))
        out.consumo_unita = "Smc"
        out.tipo = "gas"
        return 1
    return 0


class HeraParser(BaseBollettaParser):
    NAME = "hera"
    FORNITORE_DISPLAY = "Hera Comm"

    def match(self, text: str) -> bool:
        t = text.lower()
        if "hera comm" in t or "heracomm" in t:
            return True
        if "hera" in t and ("luce" in t or "gas" in t or "acqua" in t or "energia" in t):
            return True
        return False

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

        m = _RX_CODICE_UTENTE.search(text)
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

        score += _extract_consumo(text, out)

        out.confidence = min(1.0, score / 11.0)
        return out
