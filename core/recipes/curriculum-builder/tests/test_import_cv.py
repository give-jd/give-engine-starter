import io

import pytest

from modules import import_cv, storage


def _pdf_bytes(text):
    rl = pytest.importorskip("reportlab.pdfgen.canvas")
    buf = io.BytesIO()
    c = rl.Canvas(buf)
    for i, line in enumerate(text.split("\n")):
        c.drawString(72, 760 - i * 16, line)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_extract_pdf():
    data = _pdf_bytes("Maria Bianchi\nmaria@example.com")
    out = import_cv.extract_text("cv.pdf", data)
    assert "Maria Bianchi" in out and "maria@example.com" in out


def test_extract_docx():
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("Maria Bianchi")
    doc.add_paragraph("maria@example.com")
    buf = io.BytesIO()
    doc.save(buf)
    out = import_cv.extract_text("cv.docx", buf.getvalue())
    assert "Maria Bianchi" in out and "maria@example.com" in out


def test_extract_odt():
    opendocument = pytest.importorskip("odf.opendocument")
    from odf.text import P
    d = opendocument.OpenDocumentText()
    d.text.addElement(P(text="Maria Bianchi"))
    d.text.addElement(P(text="maria@example.com"))
    buf = io.BytesIO()
    d.save(buf)
    out = import_cv.extract_text("cv.odt", buf.getvalue())
    assert "Maria Bianchi" in out and "maria@example.com" in out


def test_extract_formato_non_supportato():
    with pytest.raises(ValueError):
        import_cv.extract_text("cv.txt", b"ciao")


_RAW = """Maria Bianchi
maria.bianchi@example.com  ·  +39 333 1234567
linkedin.com/in/mariabianchi

PROFILO
Ingegnera software con 8 anni di esperienza.
Focalizzata su sistemi distribuiti.

ESPERIENZA LAVORATIVA
Senior Software Engineer — ACME SpA
2021 - presente
Progettazione microservizi.

Software Engineer — Esempio Srl
2017 - 2021
Backend e-commerce.

ISTRUZIONE
Laurea Magistrale in Informatica — Politecnico di Milano
2012 - 2015

COMPETENZE
Python, Go, Kubernetes
"""


def test_heuristic_contatti():
    e = import_cv.parse_heuristic(_RAW)
    assert e["personal"]["email"] == "maria.bianchi@example.com"
    assert "333" in e["personal"]["tel"]
    assert "linkedin.com/in/mariabianchi" in e["personal"]["linkedin"]


def test_heuristic_nome():
    e = import_cv.parse_heuristic(_RAW)
    assert e["personal"]["nome"] == "Maria" and e["personal"]["cognome"] == "Bianchi"


def test_heuristic_profilo_e_sezioni():
    e = import_cv.parse_heuristic(_RAW)
    assert "sistemi distribuiti" in e["profilo"].lower()
    assert len(e["esperienze"]) >= 2
    assert any("microservizi" in x["descrizione"].lower() for x in e["esperienze"])
    assert len(e["istruzione"]) >= 1
    assert "Python" in " ".join(e["competenze"]["digitali"])


def test_heuristic_vuoto_non_crasha():
    e = import_cv.parse_heuristic("")
    assert e["personal"] == {} or all(not v for v in e["personal"].values())


def test_apply_import_riempie_solo_vuoti():
    base = storage.defaults()
    base["personal"]["nome"] = "Esistente"
    out = import_cv.apply_import(base, {"personal": {"nome": "Maria", "email": "m@x.it"}})
    assert out["personal"]["nome"] == "Esistente"       # non sovrascrive
    assert out["personal"]["email"] == "m@x.it"         # riempie il vuoto
    assert base["personal"]["email"] == ""              # originale non mutato


def test_apply_import_liste_solo_se_vuote():
    base = storage.defaults()
    out = import_cv.apply_import(base, {"esperienze": [{"ruolo": "", "azienda": "", "luogo": "",
        "dal": "", "al": "", "corrente": False, "descrizione": "blocco"}]})
    assert len(out["esperienze"]) == 1
    out2 = import_cv.apply_import(out, {"esperienze": [{"ruolo": "x", "azienda": "", "luogo": "",
        "dal": "", "al": "", "corrente": False, "descrizione": "altro"}]})
    assert len(out2["esperienze"]) == 1                 # base già piena -> non appende


def test_parse_ai_senza_chiave_none():
    assert import_cv.parse_ai("testo", None) is None
    assert import_cv.parse_ai("testo", "") is None
