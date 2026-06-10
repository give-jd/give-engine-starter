"""Test della logica pura della barra dipendenze (Fase 3, spec §4.7)."""

from __future__ import annotations

from core.shared.deps.models import Dependency, RecipeNode
from core.shared.deps.resolver import DependencyGraph
from core.shared.recipe_ui.deps_bar_logic import bar_items


def _node(slug: str, deps: list[Dependency] | None = None) -> RecipeNode:
    return RecipeNode(slug=slug, tier="catalog", version="1.0.0", deps=deps or [])


def _graph(*nodes: RecipeNode) -> DependencyGraph:
    return DependencyGraph(nodes={n.slug: n for n in nodes})


def test_mix_installed_and_not_with_ordering() -> None:
    main = _node(
        "cartella-clinica-light",
        [
            Dependency("vault-clienti", "required", "1.5.0", "Archivio cifrato"),
            Dependency("agenda-studio", "recommended", "1.2.0", "Appuntamenti"),
            Dependency("scadenze-auto-casa", "optional", None, "Promemoria"),
        ],
    )
    graph = _graph(
        main,
        _node("vault-clienti"),
        _node("agenda-studio"),
        _node("scadenze-auto-casa"),
    )
    items = bar_items(
        "cartella-clinica-light",
        graph=graph,
        installed={"vault-clienti"},  # solo la required è installata
    )

    # ordine: required, recommended, optional
    assert [i["slug"] for i in items] == [
        "vault-clienti",
        "agenda-studio",
        "scadenze-auto-casa",
    ]
    assert [i["kind"] for i in items] == ["required", "recommended", "optional"]

    installed_item = items[0]
    assert installed_item["installed"] is True
    assert installed_item["href_kind"] == "open"
    assert installed_item["label"] == "🔗 Apri vault-clienti"

    not_installed_item = items[1]
    assert not_installed_item["installed"] is False
    assert not_installed_item["href_kind"] == "add"
    assert not_installed_item["label"] == "➕ Aggiungi agenda-studio"


def test_recipe_without_deps_returns_empty() -> None:
    graph = _graph(_node("spese-casalinghe"))
    assert bar_items("spese-casalinghe", graph=graph, installed=set()) == []


def test_recipe_not_in_graph_returns_empty() -> None:
    graph = _graph(_node("spese-casalinghe"))
    assert bar_items("inesistente", graph=graph, installed=set()) == []
