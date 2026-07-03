"""Test render app.py con fake ``st`` iniettato (nessun cambio di comportamento).

Le funzioni ``render_*`` di app.py prendono ``st`` come parametro: qui vengono
esercitate con un FakeSt che restituisce valori scriptati e registra l'output.
DB sqlite ``:memory:``; le ricorrenze di test sono quotidiane (giorni 1..7)
così gli assert NON dipendono dall'orologio.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

import app  # noqa: E402
from modules import services  # noqa: E402

_TXT_ESEMPIO = """Calendario raccolta differenziata
Umido: lunedi, giovedi
Plastica e lattine: mercoledi
"""

_TXT_IGNOTO = "Lorem ipsum dolor sit amet, nessun calendario qui."


class FakeSt:
    """Stub minimale di streamlit: widget scriptati, output registrato."""

    def __init__(self, **vals):
        self.session_state: dict = {}
        self.out: list[tuple[str, str]] = []
        self._vals = vals
        self._select_q = list(vals.get("selectbox", []))
        self._text_q = list(vals.get("text_input", []))

    # --- widget (input scriptati) ---
    def slider(self, *a, **k):
        return self._vals.get("slider", 7)

    def radio(self, *a, **k):
        return self._vals.get("radio", "Manuale guidato")

    def button(self, *a, **k):
        return self._vals.get("button", False)

    def selectbox(self, label, options, **k):
        return self._select_q.pop(0) if self._select_q else options[0]

    def text_input(self, *a, **k):
        return self._text_q.pop(0) if self._text_q else ""

    def file_uploader(self, *a, **k):
        return self._vals.get("upload")

    def camera_input(self, *a, **k):
        return self._vals.get("camera")

    # --- output (registrato) ---
    def _rec(self, kind, testo):
        self.out.append((kind, str(testo)))

    def subheader(self, t):
        self._rec("subheader", t)

    def caption(self, t):
        self._rec("caption", t)

    def write(self, t):
        self._rec("write", t)

    def info(self, t):
        self._rec("info", t)

    def success(self, t):
        self._rec("success", t)

    def warning(self, t):
        self._rec("warning", t)

    def texts(self, kind):
        return [t for k, t in self.out if k == kind]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    services.init_db(c)
    yield c
    c.close()


def _seed_quotidiana(conn, nome="Umido"):
    """Frazione con raccolta ogni giorno: output non vuoto qualunque sia oggi."""
    fid = services.add_frazione(conn, {"nome": nome, "colore": "#6B4423"})
    services.add_ricorrenza(conn, {
        "frazione_id": fid, "tipo": "settimanale",
        "giorni_settimana": "1,2,3,4,5,6,7",
    })
    return fid


# --- get_conn ---


def test_get_conn_crea_schema_su_path(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "sub" / "cal.db")
    c = app.get_conn()
    try:
        assert c.execute("SELECT COUNT(*) FROM frazioni").fetchone()[0] == 0
    finally:
        c.close()


# --- render_oggi ---


def test_render_oggi_vuoto_mostra_info(conn):
    st = FakeSt()
    app.render_oggi(st, conn)
    assert any("Nessuna raccolta" in t for t in st.texts("info"))


def test_render_oggi_invia_promemoria(conn, monkeypatch):
    fid = _seed_quotidiana(conn)
    services.add_promemoria(conn, {"frazione_id": fid, "anticipo_ore": 48})
    monkeypatch.setattr(app, "_notifier_available", lambda: False)
    monkeypatch.setattr(app, "notify_os", lambda t, m: True)
    st = FakeSt(button=True)
    app.render_oggi(st, conn)
    assert st.texts("write")  # raccolte elencate
    assert any("non disponibili" in t for t in st.texts("warning"))
    assert any("inviati: 1" in t for t in st.texts("success"))
    p = conn.execute("SELECT ultimo_inviato FROM promemoria WHERE id=1").fetchone()
    assert p["ultimo_inviato"] is not None


# --- render_calendario ---


def test_render_calendario_vuoto(conn):
    st = FakeSt()
    app.render_calendario(st, conn)
    assert any("vuoto" in t.lower() for t in st.texts("info"))


def test_render_calendario_con_dati(conn):
    _seed_quotidiana(conn)
    st = FakeSt()
    app.render_calendario(st, conn)
    assert any("Umido" in t for t in st.texts("write"))


# --- render_importa: manuale / PDF / AI ---


def test_importa_manuale_crea_frazione(conn):
    st = FakeSt(radio="Manuale guidato", button=True,
                selectbox=["Umido", "settimanale"])
    app.render_importa(st, conn)
    assert st.session_state.get("ultima_frazione_id") == 1
    assert services.get_frazione(conn, 1)["nome"] == "Umido"
    assert any("creata" in t for t in st.texts("success"))


def test_importa_pdf_senza_upload(conn):
    st = FakeSt(radio="PDF assistito", upload=None)
    app.render_importa(st, conn)
    assert st.texts("warning") == []


def test_importa_pdf_illeggibile(conn):
    up = SimpleNamespace(getvalue=lambda: b"non un pdf")
    st = FakeSt(radio="PDF assistito", upload=up)
    app.render_importa(st, conn)
    assert any("Non riesco a leggere" in t for t in st.texts("warning"))


def test_importa_pdf_formato_ignoto(conn, monkeypatch):
    monkeypatch.setattr(app, "estrai_testo", lambda b: _TXT_IGNOTO)
    up = SimpleNamespace(getvalue=lambda: b"pdf")
    st = FakeSt(radio="PDF assistito", upload=up)
    app.render_importa(st, conn)
    assert any("non riconosciuto" in t for t in st.texts("warning"))


def test_importa_pdf_riconosciuto(conn, monkeypatch):
    monkeypatch.setattr(app, "estrai_testo", lambda b: _TXT_ESEMPIO)
    up = SimpleNamespace(getvalue=lambda: b"pdf")
    st = FakeSt(radio="PDF assistito", upload=up)
    app.render_importa(st, conn)
    assert st.session_state.get("parsed_calendar")
    assert any("Riconosciute" in t for t in st.texts("info"))
    assert any("Umido" in t for t in st.texts("write"))


def test_importa_ai_senza_chiave(conn):
    st = FakeSt(radio="AI (opt-in)")
    app.render_importa(st, conn)
    assert any("BYOK" in t for t in st.texts("warning"))


def test_importa_ai_con_chiave(conn, monkeypatch):
    monkeypatch.setattr("parsers.ai_extract.is_available", lambda: True)
    st = FakeSt(radio="AI (opt-in)")
    st.session_state["byok_key"] = "sk-test"
    app.render_importa(st, conn)
    assert any("v1.1" in t for t in st.texts("info"))


# --- render_regolamento ---


def test_regolamento_query_con_match(conn):
    fid = services.add_frazione(conn, {"nome": "Vetro"})
    services.add_voce_regolamento(conn, {
        "materiale": "bottiglia di vetro", "frazione_id": fid,
    })
    st = FakeSt(text_input=["vetro"])
    app.render_regolamento(st, conn)
    assert any("bottiglia di vetro" in t for t in st.texts("write"))
    assert any("BYOK" in t for t in st.texts("caption"))  # ramo senza chiave


def test_regolamento_query_senza_match(conn):
    st = FakeSt(text_input=["plutonio"])
    app.render_regolamento(st, conn)
    assert any("Nessuna corrispondenza" in t for t in st.texts("info"))


def test_regolamento_foto_classificata(conn, monkeypatch):
    monkeypatch.setattr("parsers.ai_extract.is_available", lambda: True)
    monkeypatch.setattr("parsers.ai_extract.classifica_foto",
                        lambda b, k: "vetro")
    foto = SimpleNamespace(getvalue=lambda: b"jpg")
    st = FakeSt(camera=foto)
    st.session_state["byok_key"] = "sk-test"
    app.render_regolamento(st, conn)
    assert any("vetro" in t for t in st.texts("write"))


def test_regolamento_foto_non_classificata(conn, monkeypatch):
    monkeypatch.setattr("parsers.ai_extract.is_available", lambda: True)
    monkeypatch.setattr("parsers.ai_extract.classifica_foto",
                        lambda b, k: None)
    foto = SimpleNamespace(getvalue=lambda: b"jpg")
    st = FakeSt(camera=foto)
    st.session_state["byok_key"] = "sk-test"
    app.render_regolamento(st, conn)
    assert any("non disponibile" in t for t in st.texts("info"))


# --- render_impostazioni ---


def test_impostazioni_salva_comune_e_chiave(conn):
    st = FakeSt(text_input=["Morbegno", "sk-test"])
    app.render_impostazioni(st, conn)
    assert st.session_state["comune"] == "Morbegno"
    assert st.session_state["byok_key"] == "sk-test"
    assert any("Chiave salvata" in t for t in st.texts("success"))
