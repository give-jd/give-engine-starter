"""Test parsers con tutti i campi popolati per coverage branches."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import dispatch  # noqa: E402
from parsers.enel import EnelParser, _to_iso as enel_to_iso  # noqa: E402
from parsers.eni import EniParser  # noqa: E402
from parsers.a2a import A2AParser  # noqa: E402
from parsers.iren import IrenParser  # noqa: E402
from parsers.vodafone import VodafoneParser  # noqa: E402
from parsers.tim import TimParser  # noqa: E402
from parsers.fastweb import FastwebParser  # noqa: E402
from parsers._fallback import FallbackParser  # noqa: E402


def test_enel_full_fields():
    text = """Enel Energia
POD: IT001E12345678901
Periodo: 01/04/2026 - 30/04/2026
Consumo: 245 kWh
Totale da pagare: € 67,40
IVA: € 12,15
Scadenza il 30/05/2026
"""
    r = EnelParser().parse(text)
    assert r.pod_pdr == "IT001E12345678901"
    assert r.scadenza == "2026-05-30"
    assert r.consumo_qta == pytest.approx(245.0)
    assert r.consumo_unita == "kWh"


def test_enel_smc_gas():
    text = """Enel Energia
PDR: 12345678901234
Periodo: 01/05/2026 - 31/05/2026
Consumo: 50,2 Smc
Totale bolletta: € 85,30
Scadenza il 30/06/2026
"""
    r = EnelParser().parse(text)
    assert r is not None


def test_enel_only_pdr_no_pod():
    text = "Enel Energia\nPDR: 99887766554\nTotale € 50,00"
    r = EnelParser().parse(text)
    assert r.pod_pdr == "99887766554"


def test_eni_full_fields():
    text = """Eni Plenitude
PDR: 12345678901234
Periodo dal 01/05/2026 al 31/05/2026
Consumo: 50,2 Smc
Totale fattura € 95,30
IVA: € 17,15
Scaden il 30/06/2026
"""
    r = EniParser().parse(text)
    assert r.pod_pdr == "12345678901234"
    assert r.importo_totale == pytest.approx(95.30)
    assert r.tipo == "gas"


def test_eni_pod_luce():
    text = "Eni Plenitude\nPOD: IT001E99887766\nConsumo: 100 kWh\nTotale € 50,00"
    r = EniParser().parse(text)
    assert r.pod_pdr == "IT001E99887766"


def test_a2a_full_fields_kwh():
    text = """A2A Energia
POD: IT002A2A98765432
Consumo: 180 kWh
Importo totale € 52,10
IVA € 9,40
Periodo: 15/03/2026 - 14/04/2026
Scadenza 14/05/2026
"""
    r = A2AParser().parse(text)
    assert r.pod_pdr == "IT002A2A98765432"
    assert r.consumo_qta == pytest.approx(180.0)


def test_a2a_smc():
    text = "A2A Energia\nPDR: 12121212121\nConsumo: 35 Smc\nTotale € 45,00"
    r = A2AParser().parse(text)
    assert r.consumo_unita == "Smc"
    assert r.tipo == "gas"


def test_iren_full_fields_smc():
    text = """Iren Mercato — Fattura gas
PDR: 09876543210
Consumo: 75 Smc
Totale bolletta: € 110,80
IVA: € 19,95
Periodo dal 01/02/2026 al 28/02/2026
Scadenza il 15/03/2026
"""
    r = IrenParser().parse(text)
    assert r.pod_pdr == "09876543210"
    assert r.importo_totale == pytest.approx(110.80)
    assert r.tipo == "gas"


def test_iren_kwh_luce():
    text = "Iren Mercato\nPOD: IT002I00000001\nConsumo: 200 kWh\nTotale € 80,00"
    r = IrenParser().parse(text)
    assert r.consumo_unita == "kWh"
    assert r.tipo == "luce"


def test_iren_match_alt_terms():
    text = "iren spa\nPDR: 555555555\nTotale € 30,00"
    p = IrenParser()
    assert p.match(text)
    r = p.parse(text)
    assert r is not None


def test_vodafone_full_telco():
    text = """Vodafone Italia
Linea telefonica fisso + mobile
Totale da pagare: € 29,90
IVA: € 5,40
Pagare entro 15/06/2026
"""
    r = VodafoneParser().parse(text)
    assert r.importo_totale == pytest.approx(29.90)
    assert r.tipo == "telefonia"
    assert r.consumo_qta is None


def test_tim_full_telco():
    text = """TIM S.p.A. — Telecom Italia
Linea fissa + ADSL
Totale bolletta € 34,50
IVA € 6,20
Scadenza 20/06/2026
"""
    r = TimParser().parse(text)
    assert r.importo_totale == pytest.approx(34.50)
    assert r.scadenza == "2026-06-20"


def test_fastweb_full_telco():
    text = """Fastweb fibra ultraveloce
Totale fattura € 39,95
IVA € 7,20
Entro il 25/06/2026
"""
    r = FastwebParser().parse(text)
    assert r.importo_totale == pytest.approx(39.95)
    assert r.tipo == "telefonia"


def test_fallback_with_amount_and_date():
    text = "Bolletta generica\nTotale: € 50,00\nScadenza 30/06/2026"
    r = FallbackParser().parse(text)
    assert r.importo_totale == pytest.approx(50.00)


def test_fallback_only_amount():
    text = "Importo € 100,00 da pagare"
    r = FallbackParser().parse(text)
    assert r.importo_totale is not None


def test_to_iso_2digit_year():
    assert enel_to_iso("15/06/26") == "2026-06-15"


def test_to_iso_4digit_year():
    assert enel_to_iso("15/06/2026") == "2026-06-15"


def test_to_iso_dotted():
    assert enel_to_iso("15.06.2026") == "2026-06-15"


def test_to_iso_dashed():
    assert enel_to_iso("15-06-2026") == "2026-06-15"


def test_to_iso_malformed_returns_input():
    assert enel_to_iso("15/2026") == "15/2026"


def test_parser_importo_thousands_dot():
    text = "Vodafone\nTotale: € 1.234,56"
    r = VodafoneParser().parse(text)
    assert r is not None


def test_parser_iva_only():
    text = "Iren Mercato\nPDR: 555\nIVA: € 15,00"
    r = IrenParser().parse(text)
    assert r is not None


def test_dispatch_enel_priority():
    text = "Enel Energia\nPOD: IT001E12345678901\nTotale € 50,00\nScadenza 30/05/2026"
    r = dispatch(text)
    assert r.parser_usato == "enel"


# Telco helpers + branch coverage
from parsers.vodafone import _to_iso as voda_to_iso, _to_float as voda_to_float  # noqa: E402
from parsers.tim import _to_iso as tim_to_iso, _to_float as tim_to_float  # noqa: E402
from parsers.fastweb import _to_iso as fast_to_iso, _to_float as fast_to_float  # noqa: E402
from parsers.eni import _to_iso as eni_to_iso, _to_float as eni_to_float  # noqa: E402
from parsers.a2a import _to_iso as a2a_to_iso, _to_float as a2a_to_float  # noqa: E402
from parsers.iren import _to_iso as iren_to_iso, _to_float as iren_to_float  # noqa: E402


@pytest.mark.parametrize("fn", [voda_to_iso, tim_to_iso, fast_to_iso, eni_to_iso, a2a_to_iso, iren_to_iso])
def test_telco_to_iso_2digit_year(fn):
    assert fn("15/06/26") == "2026-06-15"


@pytest.mark.parametrize("fn", [voda_to_iso, tim_to_iso, fast_to_iso, eni_to_iso, a2a_to_iso, iren_to_iso])
def test_telco_to_iso_malformed(fn):
    assert fn("15/2026") == "15/2026"


@pytest.mark.parametrize("fn", [voda_to_iso, tim_to_iso, fast_to_iso, eni_to_iso, a2a_to_iso, iren_to_iso])
def test_telco_to_iso_invalid_int(fn):
    assert fn("ab/cd/ef") == "ab/cd/ef"


@pytest.mark.parametrize("fn", [voda_to_float, tim_to_float, fast_to_float, eni_to_float, a2a_to_float, iren_to_float])
def test_telco_to_float_none_or_empty(fn):
    assert fn(None) is None
    assert fn("") is None


@pytest.mark.parametrize("fn", [voda_to_float, tim_to_float, fast_to_float, eni_to_float, a2a_to_float, iren_to_float])
def test_telco_to_float_with_comma(fn):
    assert fn("1.234,56") == pytest.approx(1234.56)


@pytest.mark.parametrize("fn", [voda_to_float, tim_to_float, fast_to_float, eni_to_float, a2a_to_float, iren_to_float])
def test_telco_to_float_without_comma(fn):
    assert fn("100") == pytest.approx(100.0)


@pytest.mark.parametrize("fn", [voda_to_float, tim_to_float, fast_to_float, eni_to_float, a2a_to_float, iren_to_float])
def test_telco_to_float_invalid(fn):
    assert fn("non-numerico") is None


def test_vodafone_with_kwh_trigger_luce_branch():
    text = "Vodafone Italia\nTotale: € 30,00\nConsumo 50 kWh"
    r = VodafoneParser().parse(text)
    assert r.consumo_qta == pytest.approx(50.0)
    assert r.consumo_unita == "kWh"
    assert r.tipo == "luce"


def test_vodafone_with_smc_trigger_gas_branch():
    text = "Vodafone Italia\nTotale: € 30,00\nConsumo 20 Smc"
    r = VodafoneParser().parse(text)
    assert r.consumo_qta == pytest.approx(20.0)
    assert r.consumo_unita == "Smc"
    assert r.tipo == "gas"


def test_tim_with_kwh_trigger():
    text = "TIM S.p.A.\nTotale: € 40,00\nConsumo 100 kWh"
    r = TimParser().parse(text)
    assert r.tipo == "luce"


def test_tim_with_smc_trigger():
    text = "TIM S.p.A.\nTotale: € 40,00\nConsumo 25 Smc"
    r = TimParser().parse(text)
    assert r.tipo == "gas"


def test_fastweb_with_kwh_trigger():
    text = "Fastweb fibra\nTotale: € 35,00\nConsumo 80 kWh"
    r = FastwebParser().parse(text)
    assert r.tipo == "luce"


def test_fastweb_with_smc_trigger():
    text = "Fastweb fibra\nTotale: € 35,00\nConsumo 15 Smc"
    r = FastwebParser().parse(text)
    assert r.tipo == "gas"


def test_telco_full_with_periodo_e_pdr():
    text = """Vodafone Italia
PDR: 9876543210
Totale: € 29,90
periodo 01/05/2026 al 31/05/2026
Scadenza 15/06/2026
"""
    r = VodafoneParser().parse(text)
    assert r.pod_pdr == "9876543210"


def test_telco_with_periodo_2digit_year():
    text = "TIM S.p.A.\nTotale: € 30,00\nperiodo 01/05/26 al 31/05/26"
    r = TimParser().parse(text)
    assert r.periodo_inizio == "2026-05-01"


def test_telco_iva_field():
    text = "Vodafone Italia\nTotale: € 29,90\nIVA 5,40"
    r = VodafoneParser().parse(text)
    assert r.iva == pytest.approx(5.40)


def test_dispatch_eni_full():
    text = """Eni Plenitude
PDR: 12345678901234
Totale € 100,00
Scaden il 15/07/2026
Periodo dal 01/06/2026 al 30/06/2026
Consumo 30 Smc
"""
    r = dispatch(text)
    assert r.parser_usato == "eni"
