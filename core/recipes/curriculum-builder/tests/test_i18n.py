from modules import i18n


def test_chiavi_pari_it_en():
    assert sorted(i18n.LABELS["it"]) == sorted(i18n.LABELS["en"])
    assert len(i18n.LABELS["it"]) > 15


def test_t_risolve_e_fallback():
    assert i18n.t("esperienze", "en") == "Work experience"
    assert i18n.t("esperienze", "xx") == i18n.LABELS["it"]["esperienze"]


def test_privacy_standard():
    assert "2016/679" in i18n.PRIVACY_TEXTS["standard-it"]
    assert "2016/679" in i18n.PRIVACY_TEXTS["standard-en"]


def test_fmt_period():
    assert i18n.fmt_period("2020-01", "2022-06", False, "it") == "01/2020 – 06/2022"
    assert i18n.fmt_period("2020-01", "", True, "it") == "01/2020 – presente"
    assert i18n.fmt_period("2020-01", "", True, "en") == "01/2020 – present"
