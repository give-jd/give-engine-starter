"""Test parser calendario: adapter esempio, registry, fallback."""

from __future__ import annotations

import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import ParsedCalendar, detect_parser, dispatch, estrai_testo  # noqa: E402
from parsers._esempio_settimanale import EsempioSettimanaleParser  # noqa: E402

_TXT_ESEMPIO = """Calendario raccolta differenziata
Umido: lunedi, giovedi
Plastica e lattine: mercoledi
Carta e cartone: martedi
"""

_TXT_IGNOTO = """Lorem ipsum dolor sit amet, nessun calendario qui.
Solo prosa senza giorni ne frazioni riconoscibili.
"""


def test_adapter_esempio_estrae_ricorrenze():
    p = EsempioSettimanaleParser()
    assert p.match(_TXT_ESEMPIO)
    cal = p.parse(_TXT_ESEMPIO)
    assert isinstance(cal, ParsedCalendar)
    frazioni = {r.frazione for r in cal.ricorrenze}
    assert "Umido" in frazioni
    umido = next(r for r in cal.ricorrenze if r.frazione == "Umido")
    assert umido.tipo == "settimanale"
    assert umido.giorni_settimana == "1,4"
    plastica = next(r for r in cal.ricorrenze if r.frazione.startswith("Plastica"))
    assert plastica.giorni_settimana == "3"
    assert cal.confidence > 0


def test_registry_riconosce_esempio():
    p = detect_parser(_TXT_ESEMPIO)
    assert p is not None
    assert p.NAME == "esempio_settimanale"


def test_registry_declina_testo_ignoto():
    assert detect_parser(_TXT_IGNOTO) is None
    assert detect_parser("") is None


def test_dispatch_ritorna_parsed_o_none():
    cal = dispatch(_TXT_ESEMPIO)
    assert cal is not None
    assert cal.ricorrenze
    assert dispatch(_TXT_IGNOTO) is None


def test_generic_text_fallback_su_date():
    # nessuna riga 'frazione: giorni' netta, ma frazione + date -> generic_text
    txt = "RAEE 12/06/2026 e 26/06/2026\nIngombranti 2026-07-01"
    p = detect_parser(txt)
    assert p is not None
    assert p.NAME == "generic_text"
    cal = p.parse(txt)
    assert any(r.tipo == "lista_date" for r in cal.ricorrenze)


def test_estrai_testo_su_pdf_non_valido():
    # bytes non-PDF -> None graceful (mai eccezione)
    assert estrai_testo(b"non un pdf") is None
