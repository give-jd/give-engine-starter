from modules import render_cv, storage


def _deep_merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _doc(patch):
    data = storage.defaults()
    _deep_merge(data, patch)
    return render_cv.render_body(data)


def test_nome_nel_header():
    html = _doc({"personal": {"nome": "Maria", "cognome": "Bianchi"}})
    assert "Maria Bianchi" in html and 'class="cv-name"' in html


def test_xss_escaped():
    html = _doc({"profilo": '<img src=x onerror="pwn()">'})
    assert "<img" not in html and "&lt;img" in html


def test_sezione_vuota_omessa():
    assert 'data-sec="esperienze"' not in _doc({})


def test_periodo_presente():
    html = _doc({"esperienze": [{"ruolo": "Dev", "azienda": "ACME", "luogo": "", "dal": "2020-01",
                                 "al": "", "corrente": True, "descrizione": ""}]})
    assert "presente" in html and 'data-sec="esperienze"' in html


def test_privacy_en_in_coda():
    html = _doc({"lang": "en", "privacy": {"tipo": "standard-en", "testoCustom": "", "dataFirma": False}})
    assert "Regulation (EU) 2016/679" in html
    assert html.rindex('data-sec="privacy"') > html.rindex("cv-main")


def test_lingue_doppia_forma():
    html = _doc({"competenze": {"lingue": [{"lingua": "Inglese", "livello": "B2"}],
                                "digitali": [], "soft": [], "patente": ""}})
    assert "cv-lang-compact" in html and "cv-lang-grid" in html


def test_document_incorpora_css_e_layout():
    data = storage.defaults()
    data["layout"] = "moderno"
    doc = render_cv.render_document(data, css=".x{color:red}")
    assert doc.startswith("<!DOCTYPE html>") and ".x{color:red}" in doc and 'class="cv--moderno"' in doc
