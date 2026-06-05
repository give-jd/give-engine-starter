"""Parser AGN Energia — bollette GPL/gas (formato 2025-2026)."""

from __future__ import annotations

import re

from .base import BaseBollettaParser, ParsedBolletta

_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}

_RX_TOTALE = re.compile(r"Totale documento[^\d]*([0-9.]+,[0-9]{2})", re.I)
_RX_TOTALE2 = re.compile(r"IMPORTO DA PAGARE\s*\n?\s*([0-9.]+,[0-9]{2})", re.I)
_RX_SCADENZA = re.compile(r"SCADENZA\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", re.I)
_RX_PERIODO_IT = re.compile(
    r"([0-9]{1,2})\s+([A-Za-zàèéìòù]+)\s+([0-9]{4})\s*-\s*"
    r"([0-9]{1,2})\s+([A-Za-zàèéìòù]+)\s+([0-9]{4})")
_RX_MATRICOLA = re.compile(r"Matricola contatore:\s*([0-9]+)", re.I)
_RX_INTEST = re.compile(r"Codice cliente:\s*[0-9]+\s*\n\s*([A-ZÀ-Ù'][A-ZÀ-Ù' ]+)")
_RX_IVA22 = re.compile(r"Aliquota al 22,00%\s+([0-9.]+,[0-9]{2})\s+([0-9.]+,[0-9]{2})", re.I)
_RX_LETTURA = re.compile(r"Utente\s+([0-9]{1,6})\b")
# DETTAGLIO LETTURE: "<matricola> <data> <lettura assoluta> Utente <consumo>"
_RX_DETTAGLIO = re.compile(
    r"\b\d{6,}\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})\s+([0-9]+)\s+Utente\b")


def _to_iso_num(d: str) -> str:
    s = d.replace(".", "/").replace("-", "/").strip()
    p = s.split("/")
    if len(p) != 3:
        return d
    dd, mm, yy = p
    if len(yy) == 2:
        yy = "20" + yy
    try:
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    except ValueError:
        return d


def _to_iso_it(dd: str, mese: str, yy: str) -> str | None:
    m = _MESI.get(mese.lower())
    if not m:
        return None
    try:
        return f"{int(yy):04d}-{m:02d}-{int(dd):02d}"
    except ValueError:
        return None


def _to_float(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


class AgnParser(BaseBollettaParser):
    NAME = "agn"
    FORNITORE_DISPLAY = "AGN Energia"
    TIPO = "gas"

    def match(self, text: str) -> bool:
        return "agn energia" in text.lower()

    def parse(self, text: str) -> ParsedBolletta:
        r = ParsedBolletta(fornitore=self.FORNITORE_DISPLAY, tipo=self.TIPO,
                           parser_usato=self.NAME)
        found = 0

        m = _RX_TOTALE.search(text) or _RX_TOTALE2.search(text)
        if m:
            r.importo_totale = _to_float(m.group(1))
            found += 1

        m = _RX_SCADENZA.search(text)
        if m:
            r.scadenza = _to_iso_num(m.group(1))
            found += 1

        m = _RX_PERIODO_IT.search(text)
        if m:
            ini = _to_iso_it(m.group(1), m.group(2), m.group(3))
            fin = _to_iso_it(m.group(4), m.group(5), m.group(6))
            if ini and fin:
                r.periodo_inizio, r.periodo_fine = ini, fin
                found += 1

        letture = [int(x) for x in _RX_LETTURA.findall(text)]
        if letture:
            r.consumo_qta = float(max(letture))
            r.consumo_unita = "Smc"
            found += 1

        # Letture assolute dal DETTAGLIO LETTURE (per integrazione letture-contatori).
        dett = [(_to_iso_num(d), float(v)) for d, v in _RX_DETTAGLIO.findall(text)]
        if dett:
            dett.sort(key=lambda x: x[0])
            r.lettura_prec_data, r.lettura_prec = dett[0]
            r.lettura_att_data, r.lettura_att = dett[-1]

        m = _RX_MATRICOLA.search(text)
        if m:
            r.pod_pdr = m.group(1)

        m = _RX_INTEST.search(text)
        if m:
            r.intestatario = m.group(1).strip()

        m = _RX_IVA22.search(text)
        if m:
            r.importo_imponibile = _to_float(m.group(1))
            r.iva = _to_float(m.group(2))

        # confidence sui 4 campi chiave (totale/scadenza/periodo/consumo)
        r.confidence = round(found / 4.0, 2)
        return r
