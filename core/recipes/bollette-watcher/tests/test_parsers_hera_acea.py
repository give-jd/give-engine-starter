"""Tests parser Hera + Acea v1.1."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import acea, dispatch, hera  # noqa: E402


HERA_BOLLETTA_LUCE = """
Hera Comm Energia Elettrica
Codice utente: 123456789
POD: IT001E12345678
Periodo di riferimento dal 01/04/2026 al 30/04/2026
Consumo: 234,5 kWh
IVA: 22,50 €
Totale da pagare: 95,40 €
Da pagare entro il 15/05/2026
"""

HERA_BOLLETTA_GAS = """
Hera Comm Gas
Codice cliente: 7890123456
PDR: 12345678901234
Periodo: dal 01/03/2026 al 31/03/2026
Consumo: 45,6 Smc
IVA: 12,30 €
Totale fattura: 78,90 €
Pagare entro il 20/04/2026
"""

HERA_BOLLETTA_ACQUA = """
Hera Comm Acqua - Servizio idrico integrato
Codice utente: 555444333
Periodo di riferimento dal 01/01/2026 al 31/03/2026
Consumo: 18,0 mc acqua
IVA: 4,50 €
Totale bolletta: 22,10 €
Scadenza il 30/04/2026
"""

ACEA_BOLLETTA_LUCE = """
Acea Energia
Codice cliente: ABC123
POD: IT001E98765432
Periodo dal 01/03/2026 al 31/03/2026
Consumo: 180,0 kWh
IVA: 19,80 €
Totale da pagare: 87,30 €
Scadenza 15/04/2026
"""

ACEA_BOLLETTA_ACQUA = """
Acea ATO2 Servizio idrico Roma
Codice cliente: XYZ789
Periodo dal 01/01/2026 al 31/03/2026
Consumo: 25,0 mc erogati
IVA: 6,20 €
Totale bolletta: 41,50 €
Pagare entro 15/05/2026
"""

NON_MATCHING = """
Enel Energia
POD: IT001E11111111
Consumo: 100 kWh
"""


class TestHeraMatch:
    def test_match_luce(self):
        p = hera.HeraParser()
        assert p.match(HERA_BOLLETTA_LUCE)

    def test_match_gas(self):
        p = hera.HeraParser()
        assert p.match(HERA_BOLLETTA_GAS)

    def test_match_acqua(self):
        p = hera.HeraParser()
        assert p.match(HERA_BOLLETTA_ACQUA)

    def test_no_match_enel(self):
        p = hera.HeraParser()
        assert not p.match(NON_MATCHING)


class TestHeraParse:
    def test_parse_luce(self):
        p = hera.HeraParser()
        r = p.parse(HERA_BOLLETTA_LUCE)
        assert r.fornitore == "Hera Comm"
        assert r.pod == "IT001E12345678"
        assert r.tipo == "luce"
        assert r.consumo_unita == "kWh"
        assert r.importo_totale == pytest.approx(95.40)
        assert r.scadenza == "2026-05-15"
        assert r.confidence > 0.5

    def test_parse_gas(self):
        p = hera.HeraParser()
        r = p.parse(HERA_BOLLETTA_GAS)
        assert r.pdr == "12345678901234"
        assert r.tipo == "gas"
        assert r.consumo_unita == "Smc"
        assert r.importo_totale == pytest.approx(78.90)

    def test_parse_acqua(self):
        p = hera.HeraParser()
        r = p.parse(HERA_BOLLETTA_ACQUA)
        assert r.tipo == "acqua"
        assert r.consumo_unita == "mc"


class TestAceaMatch:
    def test_match_luce(self):
        p = acea.AceaParser()
        assert p.match(ACEA_BOLLETTA_LUCE)

    def test_match_acqua_ato2(self):
        p = acea.AceaParser()
        assert p.match(ACEA_BOLLETTA_ACQUA)

    def test_no_match_enel(self):
        p = acea.AceaParser()
        assert not p.match(NON_MATCHING)


class TestAceaParse:
    def test_parse_luce(self):
        p = acea.AceaParser()
        r = p.parse(ACEA_BOLLETTA_LUCE)
        assert r.fornitore == "Acea Energia"
        assert r.pod == "IT001E98765432"
        assert r.tipo == "luce"
        assert r.importo_totale == pytest.approx(87.30)

    def test_parse_acqua(self):
        p = acea.AceaParser()
        r = p.parse(ACEA_BOLLETTA_ACQUA)
        assert r.tipo == "acqua"
        assert r.consumo_unita == "mc"
        assert r.consumo_qta == pytest.approx(25.0)


class TestDispatchHeraAcea:
    def test_dispatch_hera(self):
        r = dispatch(HERA_BOLLETTA_LUCE)
        assert r.parser_usato == "hera"

    def test_dispatch_acea(self):
        r = dispatch(ACEA_BOLLETTA_LUCE)
        assert r.parser_usato == "acea"
