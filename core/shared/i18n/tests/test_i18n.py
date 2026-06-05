"""Tests i18n v0.1.0."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.shared.i18n import (  # noqa: E402
    LocaleNotSupportedError,
    TranslationKeyMissingError,
    __version__,
    available_locales,
    get_locale,
    reset_cache,
    set_locale,
    translate,
)


@pytest.fixture(autouse=True)
def _reset():
    set_locale("it")
    reset_cache()
    yield
    set_locale("it")
    reset_cache()


def test_version_semver():
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_supported_locales():
    assert available_locales() == ("it", "en", "es", "fr")


def test_default_locale_it():
    assert get_locale() == "it"


def test_set_locale_valid():
    set_locale("en")
    assert get_locale() == "en"


def test_set_locale_invalid():
    with pytest.raises(LocaleNotSupportedError):
        set_locale("klingon")


def test_translate_it():
    assert translate("common.save") == "Salva"


def test_translate_en():
    assert translate("common.save", locale="en") == "Save"


def test_translate_es():
    assert translate("common.save", locale="es") == "Guardar"


def test_translate_fr():
    assert translate("common.save", locale="fr") == "Enregistrer"


def test_translate_nested():
    assert translate("recipe.farmacia.title") == "Studio Farmacia"


def test_translate_uses_current_locale():
    set_locale("fr")
    assert translate("common.cancel") == "Annuler"


def test_translate_with_format():
    msg = translate("ui.n_results", n=42)
    assert "42" in msg


def test_translate_unknown_key_raises():
    with pytest.raises(TranslationKeyMissingError):
        translate("nope.does.not.exist")


def test_translate_unknown_locale_raises():
    with pytest.raises(LocaleNotSupportedError):
        translate("common.save", locale="klingon")


def test_fallback_to_it():
    from core.shared.i18n import _cache  # noqa: WPS437
    _cache["it"] = {"only_it": "solo in italiano"}
    _cache["en"] = {"common": {}}
    assert translate("only_it", locale="en") == "solo in italiano"


def test_fallback_disabled_raises():
    from core.shared.i18n import _cache  # noqa: WPS437
    _cache["it"] = {"only_it": "x"}
    _cache["en"] = {"common": {}}
    with pytest.raises(TranslationKeyMissingError):
        translate("only_it", locale="en", fallback_to_it=False)


def test_recipe_keys_all_locales():
    for loc in available_locales():
        for recipe in ("farmacia", "rspp", "agricoltura_bio"):
            t = translate(f"recipe.{recipe}.title", locale=loc)
            assert isinstance(t, str)
            assert len(t) > 0


def test_common_yes_each_locale():
    expected = {"it": "Sì", "en": "Yes", "es": "Sí", "fr": "Oui"}
    for loc, val in expected.items():
        assert translate("common.yes", locale=loc) == val
