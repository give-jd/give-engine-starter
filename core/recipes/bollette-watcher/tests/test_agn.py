"""Test parser AGN Energia (GPL/gas) — estratto rappresentativo del PDF reale."""

from __future__ import annotations

import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import dispatch  # noqa: E402
from parsers.agn import AgnParser  # noqa: E402

_TXT = """AGN ENERGIA Spa
Via Amalfi 6
Fattura n 7018/5 del 28/02/2026
Periodo di fatturazione
28 Agosto 2025 - 28 Febbraio 2026
Codice cliente: 742142
AMIRA GIANDIEGO
Matricola contatore: 62604597
Totale documento (e) 1.659,79
SCADENZA 31/03/2026
DETTAGLIO LETTURE
62604597 27/08/2025 721 Utente 0
62604597 28/02/2026 1063 Utente 342
RIEPILOGO IVA
Aliquota al 22,00% 1.433,26 315,32
"""


def test_agn_matches():
    assert AgnParser().match(_TXT) is True


def test_agn_dispatch_uses_agn():
    r = dispatch(_TXT)
    assert r.parser_usato == "agn"
    assert r.tipo == "gas"


def test_agn_fields():
    r = dispatch(_TXT)
    assert r.importo_totale == 1659.79
    assert r.scadenza == "2026-03-31"
    assert r.periodo_inizio == "2025-08-28"
    assert r.periodo_fine == "2026-02-28"
    assert r.consumo_qta == 342.0
    assert r.consumo_unita == "Smc"
    assert r.pod_pdr == "62604597"
    assert r.importo_imponibile == 1433.26
    assert r.iva == 315.32
    assert r.confidence >= 0.9  # 4/4 campi chiave


def test_agn_letture_assolute():
    r = dispatch(_TXT)
    assert r.lettura_prec == 721.0
    assert r.lettura_prec_data == "2025-08-27"
    assert r.lettura_att == 1063.0
    assert r.lettura_att_data == "2026-02-28"
