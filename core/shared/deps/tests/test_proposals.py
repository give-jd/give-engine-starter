from core.shared.deps.models import Dependency, RecipeNode
from core.shared.deps.resolver import DependencyGraph, companions, proposals


def _node_with(*deps: Dependency) -> RecipeNode:
    return RecipeNode(slug="X", tier="catalog", version="1.0.0", deps=list(deps))


def _graph(node: RecipeNode) -> DependencyGraph:
    return DependencyGraph(nodes={node.slug: node})


def test_proposals_returns_recommended_and_optional_not_installed():
    node = _node_with(
        Dependency("req", "required", None, ""),
        Dependency("rec", "recommended", None, "consigliata"),
        Dependency("opt", "optional", None, "facoltativa"),
    )
    graph = _graph(node)
    result = proposals("X", graph=graph, installed=set())
    assert [d.slug for d in result] == ["rec", "opt"]


def test_proposals_excludes_installed():
    node = _node_with(
        Dependency("rec", "recommended", None, ""),
        Dependency("opt", "optional", None, ""),
    )
    result = proposals("X", graph=_graph(node), installed={"rec"})
    assert [d.slug for d in result] == ["opt"]


def test_companions_alias_is_recommended_plus_optional():
    node = _node_with(
        Dependency("req", "required", None, ""),
        Dependency("rec", "recommended", None, ""),
        Dependency("opt", "optional", None, ""),
    )
    assert companions("X", graph=_graph(node)) == ["rec", "opt"]
