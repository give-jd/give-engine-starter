import json

import pytest

from modules import storage


@pytest.fixture
def con(tmp_path):
    return storage.init_db(str(tmp_path / "t.db"))


def test_defaults_schema1():
    d = storage.defaults()
    assert d["schema"] == 1 and d["layout"] == "europass" and d["privacy"]["tipo"] == "standard-it"


def test_crud_multi_cv(con):
    d = storage.defaults()
    d["profilo"] = "Dev"
    i1 = storage.save_cv(con, None, "Candidatura A", d)
    i2 = storage.save_cv(con, None, "Candidatura B", storage.defaults())
    assert len(storage.list_cvs(con)) == 2
    assert storage.load_cv(con, i1)["profilo"] == "Dev"
    storage.save_cv(con, i1, "Candidatura A2", storage.load_cv(con, i1))
    assert len(storage.list_cvs(con)) == 2          # upsert, non duplica
    storage.delete_cv(con, i2)
    assert len(storage.list_cvs(con)) == 1


def test_roundtrip_json_compatibile_prototipo():
    d = storage.defaults()
    d["esperienze"] = [{"ruolo": "Dev", "azienda": "ACME", "luogo": "",
                        "dal": "2020-01", "al": "", "corrente": True, "descrizione": ""}]
    out = storage.import_json(storage.export_json(d))
    assert out["esperienze"][0]["azienda"] == "ACME" and out["schema"] == 1


def test_import_scarta_chiavi_ignote_e_rifiuta_invalido():
    out = storage.import_json(json.dumps({"schema": 1, "profilo": "X", "hacker": "no"}))
    assert out["profilo"] == "X" and "hacker" not in out
    with pytest.raises(ValueError):
        storage.import_json("{nope")
