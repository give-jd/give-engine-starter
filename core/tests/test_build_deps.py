"""Test del modulo puro core.build_deps (Fase 2, §4.6).

Usa grafi sintetici e monkeypatcha installed_registry.list_installed.
Nessuna dipendenza da FastAPI.
"""

from __future__ import annotations

import core.build_deps as build_deps
from core.shared.deps.models import Dependency, RecipeNode
from core.shared.deps.resolver import DependencyGraph


def _node(slug: str, tier: str = "starter", deps: list[Dependency] | None = None) -> RecipeNode:
    return RecipeNode(slug=slug, tier=tier, version="1.0.0", deps=deps or [])


def _graph(*nodes: RecipeNode) -> DependencyGraph:
    return DependencyGraph(nodes={n.slug: n for n in nodes})


def _req(slug: str) -> Dependency:
    return Dependency(slug=slug, kind="required", min_version=None, reason="")


def _rec(slug: str, reason: str = "consigliata") -> Dependency:
    return Dependency(slug=slug, kind="recommended", min_version=None, reason=reason)


def _opt(slug: str, reason: str = "opzionale") -> Dependency:
    return Dependency(slug=slug, kind="optional", min_version=None, reason=reason)


def test_required_transitive_queued():
    # main -> mid (required) -> base (required)
    g = _graph(
        _node("base"),
        _node("mid", deps=[_req("base")]),
        _node("main", deps=[_req("mid")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed=set(), user_tier="starter")
    assert plan.blocked is False
    assert plan.blocking_slugs == []
    # base prima di mid (ordine topologico)
    assert plan.required_queue == ["base", "mid"]


def test_installed_required_excluded():
    g = _graph(
        _node("base"),
        _node("main", deps=[_req("base")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed={"base"}, user_tier="starter")
    assert plan.required_queue == []
    assert plan.blocked is False


def test_required_not_covered_blocks():
    # main starter dipende da una required catalog -> non coperta su starter
    g = _graph(
        _node("premium", tier="catalog"),
        _node("main", deps=[_req("premium")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed=set(), user_tier="starter")
    assert plan.blocked is True
    assert plan.blocking_slugs == ["premium"]
    # la bloccante NON va in coda
    assert "premium" not in plan.required_queue


def test_required_covered_on_catalog():
    g = _graph(
        _node("premium", tier="catalog"),
        _node("main", tier="catalog", deps=[_req("premium")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed=set(), user_tier="catalog")
    assert plan.blocked is False
    assert plan.required_queue == ["premium"]


def test_recommended_preselected_optional_not():
    g = _graph(
        _node("reco"),
        _node("opt"),
        _node("main", deps=[_rec("reco"), _opt("opt")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed=set(), user_tier="starter")
    by_slug = {p["slug"]: p for p in plan.proposals}
    assert by_slug["reco"]["kind"] == "recommended"
    assert by_slug["reco"]["preselected"] is True
    assert by_slug["reco"]["covered"] is True
    assert by_slug["opt"]["kind"] == "optional"
    assert by_slug["opt"]["preselected"] is False


def test_soft_not_covered_is_upsell():
    # recommended di tier catalog su utente starter: covered False, non preselezionata
    g = _graph(
        _node("reco", tier="catalog"),
        _node("main", deps=[_rec("reco")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed=set(), user_tier="starter")
    p = plan.proposals[0]
    assert p["slug"] == "reco"
    assert p["covered"] is False
    assert p["preselected"] is False  # non coperta -> non preselezionata anche se recommended


def test_installed_soft_not_proposed():
    g = _graph(
        _node("reco"),
        _node("main", deps=[_rec("reco")]),
    )
    plan = build_deps.plan_dependencies("main", graph=g, installed={"reco"}, user_tier="starter")
    assert plan.proposals == []


def test_finalize_queue_unisce_e_dedup():
    g = _graph(
        _node("base"),
        _node("mid", deps=[_req("base")]),
        _node("sa"),
        _node("sb"),
        _node("main", deps=[_req("mid"), _rec("sa"), _opt("sb")]),
    )
    queue = build_deps.finalize_queue(["base", "mid"], ["sa", "sb", "base"], graph=g)
    # required prima, soft dopo, "base" duplicata appare una sola volta all'inizio
    assert queue[:2] == ["base", "mid"]
    assert set(queue[2:]) == {"sa", "sb"}
    assert queue.count("base") == 1


def test_finalize_queue_empty():
    g = _graph(_node("main"))
    assert build_deps.finalize_queue([], [], graph=g) == []


def test_installed_slugs_monkeypatched(monkeypatch):
    import core.installed_registry as reg

    monkeypatch.setattr(
        reg,
        "list_installed",
        lambda: [{"slug": "a"}, {"slug": "b"}, {"slug": None}],
    )
    assert build_deps.installed_slugs() == {"a", "b"}
