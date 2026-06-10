from core.shared.deps.models import Dependency, RecipeNode
from core.shared.deps.resolver import DependencyGraph, validate


def _graph(*nodes: RecipeNode) -> DependencyGraph:
    return DependencyGraph(nodes={n.slug: n for n in nodes})


def test_validate_clean_graph_has_no_errors():
    a = RecipeNode("a", "starter", "1.0.0", [])
    b = RecipeNode("b", "catalog", "1.0.0", [Dependency("a", "required", "1.0.0", "x")])
    assert validate(_graph(a, b)) == []


def test_validate_missing_slug():
    b = RecipeNode("b", "catalog", "1.0.0", [Dependency("ghost", "required", None, "x")])
    errs = validate(_graph(b))
    assert any("ghost" in e and "b" in e for e in errs)


def test_validate_required_cycle():
    a = RecipeNode("a", "catalog", "1.0.0", [Dependency("b", "required", None, "")])
    b = RecipeNode("b", "catalog", "1.0.0", [Dependency("a", "required", None, "")])
    errs = validate(_graph(a, b))
    assert any("ciclo" in e.lower() for e in errs)


def test_validate_required_tier_must_be_le_recipe_tier():
    # starter recipe requiring a catalog recipe -> violation
    cat = RecipeNode("cat", "catalog", "1.0.0", [])
    star = RecipeNode("star", "starter", "1.0.0", [Dependency("cat", "required", None, "")])
    errs = validate(_graph(cat, star))
    assert any("tier" in e.lower() for e in errs)


def test_validate_bad_min_version():
    a = RecipeNode("a", "catalog", "1.0.0", [])
    b = RecipeNode("b", "catalog", "1.0.0", [Dependency("a", "required", "1.x", "")])
    errs = validate(_graph(a, b))
    assert any("versione" in e.lower() or "version" in e.lower() for e in errs)
