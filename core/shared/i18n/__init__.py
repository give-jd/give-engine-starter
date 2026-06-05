"""i18n shared module v0.1.0 — IT/EN/ES/FR.

Italian-first (Punto 18). Default locale: it. ES + FR baseline Q2-2029.

Pattern:
    from core.shared.i18n import translate, set_locale
    set_locale("es")
    translate("recipe.farmacia.title")
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
_VERSION_FILE = _MODULE_DIR / "I18N_VERSION"
_LOCALES_DIR = _MODULE_DIR / "locales"

__version__ = _VERSION_FILE.read_text(encoding="utf-8").strip()

_DEFAULT_LOCALE = "it"
_SUPPORTED = ("it", "en", "es", "fr")

_lock = threading.RLock()
_current_locale: str = _DEFAULT_LOCALE
_cache: dict[str, dict] = {}


class LocaleNotSupportedError(ValueError):
    """Locale richiesta non in lista supportate."""


class TranslationKeyMissingError(KeyError):
    """Chiave traduzione non trovata."""


def available_locales() -> tuple[str, ...]:
    return _SUPPORTED


def get_locale() -> str:
    with _lock:
        return _current_locale


def set_locale(locale: str) -> None:
    if locale not in _SUPPORTED:
        raise LocaleNotSupportedError(
            f"Locale '{locale}' non supportata. Disponibili: {_SUPPORTED}"
        )
    with _lock:
        global _current_locale
        _current_locale = locale


def _load_locale(locale: str) -> dict:
    with _lock:
        if locale in _cache:
            return _cache[locale]
        path = _LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            raise LocaleNotSupportedError(
                f"File traduzioni mancante: {path.name}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        _cache[locale] = data
        return data


def _resolve(d: dict, key: str) -> str | None:
    parts = key.split(".")
    cur: object = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur if isinstance(cur, str) else None


def translate(key: str, locale: str | None = None,
              *, fallback_to_it: bool = True, **fmt: object) -> str:
    if locale is None:
        locale = get_locale()
    if locale not in _SUPPORTED:
        raise LocaleNotSupportedError(f"Locale '{locale}' non supportata")
    data = _load_locale(locale)
    value = _resolve(data, key)
    if value is None and fallback_to_it and locale != _DEFAULT_LOCALE:
        value = _resolve(_load_locale(_DEFAULT_LOCALE), key)
    if value is None:
        raise TranslationKeyMissingError(
            f"Chiave '{key}' non trovata (locale={locale})"
        )
    if fmt:
        try:
            return value.format(**fmt)
        except (KeyError, IndexError) as exc:
            raise TranslationKeyMissingError(
                f"Format placeholder mancante in '{key}': {exc}"
            ) from exc
    return value


def reset_cache() -> None:
    with _lock:
        _cache.clear()


__all__ = (
    "__version__",
    "translate",
    "set_locale",
    "get_locale",
    "available_locales",
    "reset_cache",
    "LocaleNotSupportedError",
    "TranslationKeyMissingError",
)
