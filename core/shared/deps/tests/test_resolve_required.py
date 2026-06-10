import pytest

from core.shared.deps.exceptions import DependencyCycle
from core.shared.deps.models import Dependency, RecipeNode
from core.shared.deps.resolver import DependencyGraph, resolve_required


def _graph(*nodes: RecipeNode) -> DependencyGraph:
    return DependencyGraph(nodes={n.slug: n for n in nodes})


def _node(slug: str, *required: str) -> RecipeNode:
    deps = [Dependency(s, "required", None, "") for s in required]
    return RecipeNode(slug=slug, tier="catalog", version="1.0.0", deps=deps)


def test_resolve_transitive_topological_order():
    # C -> B -> A : install order must be [A, B]
    graph = _graph(_node("A"), _node("B", "A"), _node("C", "B"))
    assert resolve_required("C", graph=graph, installed=set()) == ["A", "B"]


def test_resolve_excludes_already_installed():
    graph = _graph(_node("A"), _node("B", "A"), _node("C", "B"))
    assert resolve_required("C", graph=graph, installed={"A"}) == ["B"]


def test_resolve_no_required_returns_empty():
    graph = _graph(_node("A"))
    assert resolve_required("A", graph=graph, installed=set()) == []


def test_resolve_skips_missing_required_slug():
    # 'B' richiede 'ghost' che non esiste nel grafo: non deve essere accodato
    graph = _graph(_node("A"), _node("B", "ghost"))
    assert resolve_required("B", graph=graph, installed=set()) == []


def test_resolve_detects_cycle():
    graph = _graph(_node("A", "B"), _node("B", "A"))
    with pytest.raises(DependencyCycle):
        resolve_required("A", graph=graph, installed=set())
