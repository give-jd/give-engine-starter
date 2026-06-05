"""Unit tests for 7 vendor parsers + dispatch + fallback."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import dispatch, ALL_PARSERS, FALLBACK
from parsers.enel import EnelParser
from parsers.eni import EniParser
from parsers.a2a import A2AParser
from parsers.iren import IrenParser
from parsers.vodafone import VodafoneParser
from parsers.tim import TimParser
from parsers.fastweb import FastwebParser
from parsers.edison import EdisonParser


ENEL_TEXT = """
Enel Energia — Bolletta luce
POD: IT001E12345678901
Periodo: 01/04/2026 - 30/04/2026
Consumo: 245 kWh
Totale da pagare: € 67,40
Scadenza il 30/05/2026
"""

ENI_TEXT = """
Eni Plenitude Gas e Luce
PDR: 12345678901234
Periodo dal 01/05/2026 al 31/05/2026
Consumo: 50,2 Smc
Totale fattura € 95,30
Scaden il 30/06/2026
"""

A2A_TEXT = """
A2A Energia
POD: IT002A2A98765432
Consumo: 180 kWh
Importo totale € 52,10
Periodo: 15/03/2026 - 14/04/2026
Scadenza 14/05/2026
"""

IREN_TEXT = """
Iren Mercato — Fattura gas
PDR: 09876543210
Consumo: 75 Smc
Totale bolletta: € 110,80
Periodo dal 01/02/2026 al 28/02/2026
"""

VODAFONE_TEXT = """
Vodafone Italia
Linea telefonica
Totale da pagare: € 29,90
Pagare entro 15/06/2026
"""

TIM_TEXT = """
TIM S.p.A. — Telecom Italia
Totale bolletta € 34,50
Scadenza 20/06/2026
"""

FASTWEB_TEXT = """
Fastweb fibra ultraveloce
Totale fattura € 39,95
Entro il 25/06/2026
"""


def test_match_enel_only_on_enel_text():
    assert EnelParser().match(ENEL_TEXT)
    assert not EnelParser().match(ENI_TEXT)


def test_match_eni_plenitude():
    assert EniParser().match(ENI_TEXT)


def test_match_a2a():
    assert A2AParser().match(A2A_TEXT)


def test_match_iren():
    assert IrenParser().match(IREN_TEXT)


def test_match_vodafone():
    assert VodafoneParser().match(VODAFONE_TEXT)


def test_match_tim():
    assert TimParser().match(TIM_TEXT)


def test_match_fastweb():
    assert FastwebParser().match(FASTWEB_TEXT)


EDISON_TEXT = """
Edison Energia — Bolletta luce
POD: IT001E22334455667
Periodo dal 01/04/2026 al 30/04/2026
Consumo: 180 kWh
Totale da pagare: € 58,90
IVA: € 10,55
Scadenza il 30/05/2026
"""


def test_match_edison():
    assert EdisonParser().match(EDISON_TEXT)
    assert not EdisonParser().match(ENEL_TEXT)


def test_parse_edison_extracts_pod():
    r = EdisonParser().parse(EDISON_TEXT)
    assert r.pod_pdr == "IT001E22334455667"
    assert r.tipo == "luce"
    assert r.importo_totale == pytest.approx(58.90)
    assert r.scadenza == "2026-05-30"
    assert r.consumo_unita == "kWh"


def test_parse_eni_extracts_pdr():
    r = EniParser().parse(ENI_TEXT)
    assert r.pod_pdr == "12345678901234"
    assert r.importo_totale == pytest.approx(95.30)
    assert r.scadenza == "2026-06-30"
    assert r.consumo_qta == pytest.approx(50.2)
    assert r.consumo_unita == "Smc"
    assert r.tipo == "gas"


def test_parse_a2a_kwh_overrides_tipo_luce():
    r = A2AParser().parse(A2A_TEXT)
    assert r.tipo == "luce"
    assert r.consumo_unita == "kWh"
    assert r.importo_totale == pytest.approx(52.10)


def test_parse_iren_smc_keeps_gas():
    r = IrenParser().parse(IREN_TEXT)
    assert r.tipo == "gas"
    assert r.consumo_unita == "Smc"
    assert r.consumo_qta == pytest.approx(75.0)


def test_parse_telco_no_consumo():
    r = VodafoneParser().parse(VODAFONE_TEXT)
    assert r.consumo_qta is None
    assert r.tipo == "telefonia"
    assert r.importo_totale == pytest.approx(29.90)


def test_parse_confidence_high_when_full():
    r = EniParser().parse(ENI_TEXT)
    assert r.confidence >= 0.8


def test_parse_confidence_low_when_sparse():
    r = EniParser().parse("Eni Plenitude solo header")
    assert r.confidence < 0.5


def test_dispatch_routes_to_correct_parser():
    assert dispatch(ENEL_TEXT).parser_usato == "enel"
    assert dispatch(ENI_TEXT).parser_usato == "eni"
    assert dispatch(A2A_TEXT).parser_usato == "a2a"
    assert dispatch(IREN_TEXT).parser_usato == "iren"
    assert dispatch(VODAFONE_TEXT).parser_usato == "vodafone"
    assert dispatch(TIM_TEXT).parser_usato == "tim"
    assert dispatch(FASTWEB_TEXT).parser_usato == "fastweb"


def test_dispatch_fallback_unknown_text():
    r = dispatch("Bolletta non riconosciuta da nessun vendor")
    assert r is not None


def test_dispatch_handles_empty_text():
    r = dispatch("")
    assert r is not None


def test_parser_handles_dotted_year_format():
    text = "Eni Plenitude\nPDR: 11111111111\nTotale € 100,00\nScadenza il 01.07.2026"
    r = EniParser().parse(text)
    assert r.scadenza == "2026-07-01"


def test_parser_handles_2digit_year():
    text = "Eni Plenitude\nPDR: 11111111111\nScaden il 15/06/26"
    r = EniParser().parse(text)
    assert r.scadenza == "2026-06-15"
