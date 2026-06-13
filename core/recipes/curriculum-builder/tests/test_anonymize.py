from modules import anonymize, render_cv, storage


def _cv():
    d = storage.defaults()
    d["personal"].update({"nome": "Maria", "cognome": "Bianchi", "email": "maria@example.com",
                          "tel": "+39 333 0000000", "indirizzo": "Via Esempio 1, Milano",
                          "dataNascita": "1990-05-12", "nazionalita": "Italiana",
                          "linkedin": "linkedin.com/in/mb", "sito": "mb.example",
                          "foto": "data:image/png;base64,AAAA"})
    d["profilo"] = "Ingegnera software."
    d["esperienze"] = [{"ruolo": "Dev", "azienda": "ACME", "luogo": "Milano",
                        "dal": "2020-01", "al": "", "corrente": True, "descrizione": ""}]
    return d


def test_iniziali_e_campi_mascherati():
    a = anonymize.anonymize(_cv())
    p = a["personal"]
    assert p["nome"] == "M." and p["cognome"] == "B."
    for k in ("email", "tel", "indirizzo", "dataNascita", "nazionalita", "linkedin", "sito"):
        assert p[k] == ""
    assert p["foto"] is None


def test_contenuti_restano():
    a = anonymize.anonymize(_cv())
    assert a["profilo"] == "Ingegnera software."
    assert a["esperienze"][0]["azienda"] == "ACME"


def test_originale_non_mutato():
    cv = _cv()
    anonymize.anonymize(cv)
    assert cv["personal"]["nome"] == "Maria" and cv["personal"]["foto"] is not None


def test_render_anonimo_pulito():
    html = render_cv.render_body(anonymize.anonymize(_cv()))
    assert "Maria" not in html and "maria@example.com" not in html
    assert "<img" not in html
    assert "M. B." in html


def test_nome_vuoto_non_crasha():
    d = storage.defaults()
    a = anonymize.anonymize(d)
    assert a["personal"]["nome"] == "" and a["personal"]["cognome"] == ""


def test_print_preview_due_varianti_e_toolbar():
    cv = _cv()
    doc = render_cv.render_print_preview(cv, anonymize.anonymize(cv), css=".x{}")
    assert 'id="cv-full"' in doc and 'id="cv-anon"' in doc
    assert "window.print()" in doc and "no-print" in doc
    assert 'class="cv-sheet cv--europass hide"' in doc          # anon parte nascosta
    assert doc.count("maria@example.com") == 1                   # email solo nella variante completa
    assert "M. B." in doc                                        # iniziali nella variante anonima
    assert "Annulla" in doc and "Completo" in doc and "Anonimo" in doc
