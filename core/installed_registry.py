"""Registro delle ricette installate (slug, porta, stato), su prefs di sistema.

Evolve la chiave legacy ``built_recipes`` (lista piatta di slug) in
``installed_recipes`` (lista di dict). Legge entrambi i formati in modo
retro-compatibile.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.system import get_pref as _get_pref
from core.system import prefs_transaction as _prefs_transaction
from core.system import set_pref as _set_pref

_KEY = "installed_recipes"
_LEGACY_KEY = "built_recipes"


def _load() -> list[dict]:
    rows = _get_pref(_KEY, None)
    if isinstance(rows, list) and (not rows or isinstance(rows[0], dict)):
        return list(rows)
    # migrazione legacy: lista piatta di slug
    legacy = _get_pref(_LEGACY_KEY, []) or []
    return [
        {
            "slug": str(s),
            "version": None,
            "porta": None,
            "status": "installed",
            "output_dir": None,
            "installed_at": None,
        }
        for s in legacy
    ]


def _save(rows: list[dict]) -> None:
    _set_pref(_KEY, rows)


def register_installed(
    slug: str, *, port: int | None, version: str | None, output_dir: str | None,
    expose_lan: bool | None = None,
) -> None:
    """Registra (o aggiorna) una ricetta come installata.

    Args:
        slug: Id ricetta.
        port: Porta locale assegnata.
        version: Versione installata.
        output_dir: Directory dell'app generata.
        expose_lan: Scelta "usa da smartphone" fatta al build (bind 0.0.0.0).
            None se sconosciuta (ricette ready-app: si usa la pref globale).
    """
    # Transazione: load→muta lista→save sotto un unico lock, così due
    # register_installed concorrenti (build + open) non si perdono a vicenda.
    with _prefs_transaction():
        rows = [r for r in _load() if r.get("slug") != slug]
        rows.append(
            {
                "slug": slug,
                "version": version,
                "porta": port,
                "status": "installed",
                "output_dir": output_dir,
                "expose_lan": expose_lan,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _save(rows)


def get_row(slug: str) -> dict | None:
    """Riga di registro per ``slug``, o None se non installata."""
    for r in _load():
        if r.get("slug") == slug:
            return r
    return None


def is_installed(slug: str) -> bool:
    """True se ``slug`` risulta installata."""
    return any(r.get("slug") == slug for r in _load())


def get_port(slug: str) -> int | None:
    """Porta locale registrata per ``slug``, o None se sconosciuta/non installata."""
    for r in _load():
        if r.get("slug") == slug:
            return r.get("porta")
    return None


def list_installed() -> list[dict]:
    """Tutte le ricette installate (lista di dict)."""
    return _load()
