"""UI test (streamlit AppTest) per app.py — flusso principale.

HOME -> tmp cosi' il DB vive su tmp_path (nessun dato reale). Il seed usa una
ricorrenza quotidiana (giorni 1..7): gli assert non dipendono dall'orologio.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from modules import services  # noqa: E402

_APP = str(RECIPE_DIR / "app.py")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _seed_db(home: Path) -> None:
    db = home / ".givengine" / "data" / "calendario-comunale-rifiuti.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    services.init_db(conn)
    fid = services.add_frazione(conn, {"nome": "Umido", "colore": "#6B4423"})
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale",
        "giorni_settimana": "1,2,3,4,5,6,7",
    })
    services.add_voce_regolamento(conn, {
        "materiale": "bottiglia di vetro", "frazione_id": fid,
    })
    conn.close()


def test_main_runs_su_db_vuoto(home):
    at = AppTest.from_file(_APP, default_timeout=60).run()
    assert not at.exception
    assert len(at.tabs) == 5
    # DB vuoto -> info "Nessuna raccolta" nella tab Oggi
    assert any("Nessuna raccolta" in i.value for i in at.info)


def test_main_con_db_popolato(home):
    _seed_db(home)
    at = AppTest.from_file(_APP, default_timeout=60).run()
    assert not at.exception
    # ricorrenza quotidiana -> raccolte elencate in Oggi/Calendario
    assert any("Umido" in m.value for m in at.markdown)
    # bottone promemoria presente (nessun promemoria seedato -> 0 inviati)
    at.button[0].click().run()
    assert not at.exception
    assert any("Promemoria inviati: 0" in s.value for s in at.success)


def test_ricerca_regolamento(home):
    _seed_db(home)
    at = AppTest.from_file(_APP, default_timeout=60).run()
    # primo text_input = query "Dove butto X?" (tab Regolamento)
    at.text_input[0].set_value("vetro").run()
    assert not at.exception
    assert any("bottiglia di vetro" in m.value for m in at.markdown)
