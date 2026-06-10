"""Test della logica pura del launcher (Fase 3, spec §4.7)."""

from __future__ import annotations

from core.launcher_logic import decide_open


def _port_map(mapping: dict[str, int | None]):
    return lambda slug: mapping.get(slug)


def test_not_installed_redirects_to_install() -> None:
    action = decide_open(
        "vault-clienti",
        installed=set(),
        get_port=_port_map({}),
        is_covered=lambda _s: True,
    )
    assert action == {"action": "install_redirect", "slug": "vault-clienti"}


def test_installed_but_not_covered_redirects_to_pricing() -> None:
    action = decide_open(
        "vault-clienti",
        installed={"vault-clienti"},
        get_port=_port_map({"vault-clienti": 8511}),
        is_covered=lambda _s: False,
    )
    assert action == {"action": "pricing_redirect"}


def test_installed_and_covered_opens_with_port() -> None:
    action = decide_open(
        "vault-clienti",
        installed={"vault-clienti"},
        get_port=_port_map({"vault-clienti": 8511}),
        is_covered=lambda _s: True,
    )
    assert action == {"action": "open", "slug": "vault-clienti", "port": 8511}


def test_installed_covered_unknown_port_is_none() -> None:
    # porta sconosciuta nel registro → None: l'orchestrator dovrà spawnare.
    action = decide_open(
        "agenda-studio",
        installed={"agenda-studio"},
        get_port=_port_map({"agenda-studio": None}),
        is_covered=lambda _s: True,
    )
    assert action == {"action": "open", "slug": "agenda-studio", "port": None}
