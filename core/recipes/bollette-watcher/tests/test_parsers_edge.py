"""Edge cases parsers: no match, empty, malformed — coverage branches."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import dispatch  # noqa: E402
from parsers.enel import EnelParser  # noqa: E402
from parsers.eni import EniParser  # noqa: E402
from parsers.a2a import A2AParser  # noqa: E402
from parsers.iren import IrenParser  # noqa: E402
from parsers.vodafone import VodafoneParser  # noqa: E402
from parsers.tim import TimParser  # noqa: E402
from parsers.fastweb import FastwebParser  # noqa: E402
from parsers._fallback import FallbackParser  # noqa: E402


ALL_PARSER_CLASSES = [
    EnelParser, EniParser, A2AParser, IrenParser,
    VodafoneParser, TimParser, FastwebParser, FallbackParser,
]


@pytest.mark.parametrize("ParserCls", ALL_PARSER_CLASSES)
def test_parser_empty_text(ParserCls):
    p = ParserCls()
    r = p.parse("")
    assert r is not None
    assert r.confidence < 0.5


@pytest.mark.parametrize("ParserCls", ALL_PARSER_CLASSES)
def test_parser_only_header(ParserCls):
    p = ParserCls()
    name_map = {
        "EnelParser": "Enel Energia",
        "EniParser": "Eni Plenitude",
        "A2AParser": "A2A Energia",
        "IrenParser": "Iren Mercato",
        "VodafoneParser": "Vodafone Italia",
        "TimParser": "TIM S.p.A.",
        "FastwebParser": "Fastweb",
        "FallbackParser": "vendor sconosciuto",
    }
    text = name_map.get(ParserCls.__name__, "header only")
    r = p.parse(text)
    assert r is not None


def test_dispatch_short_text():
    r = dispatch("X")
    assert r is not None


def test_dispatch_numbers_only():
    r = dispatch("12345 67890 100,00")
    assert r is not None


def test_dispatch_long_random():
    r = dispatch("Lorem ipsum dolor sit amet " * 50)
    assert r is not None


def test_parser_malformed_totale():
    text = "Enel Energia\nPOD: IT001E12345678901\nTotale da pagare: € non-numerico"
    r = EnelParser().parse(text)
    assert r is not None


def test_parser_malformed_data():
    text = "Eni Plenitude\nPDR: 12345678901234\nScaden il data-bizzarra"
    r = EniParser().parse(text)
    assert r is not None


def test_parser_missing_pod_pdr():
    text = "Vodafone Italia\nTotale: € 25,00"
    r = VodafoneParser().parse(text)
    assert r is not None
    assert r.pod_pdr is None


def test_parser_solo_kwh():
    text = "A2A Energia\nPOD: IT002A2A12345678\nConsumo 100 kWh totali"
    r = A2AParser().parse(text)
    assert r is not None


def test_parser_solo_smc():
    text = "Iren Mercato\nPDR: 09876543210\nConsumo 40 Smc gas"
    r = IrenParser().parse(text)
    assert r is not None


def test_parser_multiple_pod():
    text = "Enel Energia\nPOD: IT001E11111111111\nPOD: IT001E99999999999\nTotale € 100,00"
    r = EnelParser().parse(text)
    assert r is not None


def test_parser_decimal_format():
    text = "TIM S.p.A.\nTotale bolletta € 1.234,56"
    r = TimParser().parse(text)
    assert r is not None


def test_dispatch_priority_specific():
    text = "Enel Energia\nPOD: IT001E12345678901\nTotale € 50,00"
    r = dispatch(text)
    assert r.parser_usato == "enel"


def test_dispatch_fallback():
    text = "Documento generico non identificabile"
    r = dispatch(text)
    assert r.parser_usato in ("fallback", "_fallback")


def test_parser_unicode_currency():
    text = "Fastweb fibra\nTotale fattura € 42,00"
    r = FastwebParser().parse(text)
    assert r is not None


def test_parser_html_entities():
    text = "Vodafone Italia\nTotale: &euro; 29,00"
    r = VodafoneParser().parse(text)
    assert r is not None


def test_parser_aggressive_newlines():
    text = "Enel\nEnergia\n\n\nPOD: IT001E12345678901\n\n\nTotale\n€\n100,00\n"
    r = EnelParser().parse(text)
    assert r is not None


def test_parser_with_tabs():
    text = "Eni Plenitude\tPDR:\t12345678901234\tTotale\t€\t75,00"
    r = EniParser().parse(text)
    assert r is not None


def test_fallback_with_amount():
    text = "Pago € 30,00 entro il 15/06/2026"
    r = FallbackParser().parse(text)
    assert r is not None


def test_fallback_no_amount():
    text = "Nessun importo qui"
    r = FallbackParser().parse(text)
    assert r is not None
    assert r.confidence < 0.5
