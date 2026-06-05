"""Regressione: il CSV MIMIT è pipe-delimited (`|`), non `;`.

Con il delimiter sbagliato l'intera riga finiva in un'unica colonna, idImpianto
non veniva letto e la ricerca per comune restava vuota.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

import app  # noqa: E402

# Formato reale MIMIT (riga "Estrazione del" + header + dati), pipe-delimited.
_ANAG = (
    "Estrazione del 2026-06-03\n"
    "idImpianto|Gestore|Bandiera|Tipo Impianto|Nome Impianto|Indirizzo|Comune|Provincia|Latitudine|Longitudine\n"
    "12345|ROSSI SRL|Q8|Stradale|Area 1|VIA ROMA 1|MILANO|MI|45.4642|9.19\n"
)


def test_sniff_delim_detects_pipe():
    assert app._sniff_delim("idImpianto|Gestore|Bandiera") == "|"
    assert app._sniff_delim("idImpianto;Gestore;Bandiera") == ";"


def test_pipe_csv_extracts_fields():
    lines = _ANAG.splitlines()[1:]
    delim = app._sniff_delim(lines[0])
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delim)
    rows = list(reader)
    assert len(rows) == 1
    assert int(rows[0]["idImpianto"]) == 12345
    assert rows[0]["Comune"] == "MILANO"
    assert float(rows[0]["Latitudine"]) == 45.4642


def test_wrong_delim_would_lose_idimpianto():
    # dimostra il bug originale: con ';' su un file pipe, idImpianto non esiste
    lines = _ANAG.splitlines()[1:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=";")
    row = next(iter(reader))
    assert "idImpianto" not in row  # tutta la riga in un'unica colonna
