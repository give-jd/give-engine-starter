"""Pianificazione delle dipendenze in fase di build (modulo puro, no FastAPI).

Estrae la logica di Fase 2 della spec dipendenze ricette (§4.6) in funzioni pure
e testabili senza l'orchestrator: dato un grafo, il set di ricette installate e
il tier dell'utente, decide cosa bloccare, cosa installare prima (required) e
cosa proporre (recommended/optional). Il wiring nell'orchestrator resta sottile.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.shared.deps.resolver import DependencyGraph, proposals, resolve_required

# Rank dei tier: starter < catalog. All-access è trattato come catalog (stesso
# accesso al Catalogo). Mappa estendibile passando ``tier_rank`` a
# ``plan_dependencies``.
_DEFAULT_TIER_RANK: dict[str, int] = {"starter": 0, "catalog": 1, "all-access": 1}


@dataclass
class BuildDepsPlan:
    """Esito della pianificazione delle dipendenze per una build.

    Attributes:
        blocked: True se almeno una dipendenza ``required`` non è coperta dalla
            licenza dell'utente (la build principale non deve partire).
        blocking_slugs: Slug delle ``required`` non coperte dal tier.
        required_queue: Slug ``required`` non installate da costruire prima della
            principale, in ordine topologico (dipendenze prima). Esclude le
            bloccanti non coperte.
        proposals: Proposte soft (recommended + optional) non installate. Ogni
            voce è un dict ``{slug, kind, reason, covered, preselected}``.
    """

    blocked: bool = False
    blocking_slugs: list[str] = field(default_factory=list)
    required_queue: list[str] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)


def installed_slugs() -> set[str]:
    """Set degli slug attualmente installati, dal registro installati.

    Returns:
        Set di slug presenti in ``installed_registry.list_installed()``.
    """
    from core import installed_registry

    return {str(r.get("slug")) for r in installed_registry.list_installed() if r.get("slug")}


def _tier_rank(tier: str, ranks: dict[str, int]) -> int:
    return ranks.get(tier, 0)


def _is_covered(dep_tier: str, user_tier: str, ranks: dict[str, int]) -> bool:
    return _tier_rank(dep_tier, ranks) <= _tier_rank(user_tier, ranks)


def _node_tier(graph: DependencyGraph, slug: str) -> str:
    node = graph.nodes.get(slug)
    return node.tier if node is not None else "starter"


def plan_dependencies(
    recipe_id: str,
    *,
    graph: DependencyGraph,
    installed: set[str],
    user_tier: str,
    tier_rank: dict[str, int] | None = None,
) -> BuildDepsPlan:
    """Pianifica install/blocco/proposta delle dipendenze di ``recipe_id``.

    Le ``required`` non installate vengono risolte transitivamente in ordine
    topologico. Quelle non coperte dal tier utente non finiscono in coda ma
    bloccano la build (``blocked=True``). Le soft non installate diventano
    proposte (recommended pre-selezionate se coperte, optional mai pre-selezionate).

    Args:
        recipe_id: Ricetta principale che si sta costruendo.
        graph: Grafo completo delle ricette.
        installed: Slug già installati (esclusi da coda e proposte).
        user_tier: Tier della licenza utente ("starter" | "catalog" | "all-access").
        tier_rank: Mappa opzionale tier→rank; default starter=0, catalog/all-access=1.

    Returns:
        Il :class:`BuildDepsPlan` con blocco, coda required e proposte soft.
    """
    ranks = tier_rank if tier_rank is not None else _DEFAULT_TIER_RANK

    required = resolve_required(recipe_id, graph=graph, installed=installed)
    blocking: list[str] = []
    queue: list[str] = []
    for slug in required:
        if _is_covered(_node_tier(graph, slug), user_tier, ranks):
            queue.append(slug)
        else:
            blocking.append(slug)

    props: list[dict] = []
    for dep in proposals(recipe_id, graph=graph, installed=installed):
        covered = _is_covered(_node_tier(graph, dep.slug), user_tier, ranks)
        props.append(
            {
                "slug": dep.slug,
                "kind": dep.kind,
                "reason": dep.reason,
                "covered": covered,
                "preselected": dep.kind == "recommended" and covered,
            }
        )

    return BuildDepsPlan(
        blocked=bool(blocking),
        blocking_slugs=blocking,
        required_queue=queue,
        proposals=props,
    )


def _topo_index(graph: DependencyGraph) -> dict[str, int]:
    """Indice topologico globale sulle sole ``required`` (dipendenze prima)."""
    order: list[str] = []
    seen: set[str] = set()
    visiting: set[str] = set()

    def visit(slug: str) -> None:
        if slug in seen or slug in visiting:
            return
        visiting.add(slug)
        node = graph.nodes.get(slug)
        if node is not None:
            for dep in node.required:
                visit(dep.slug)
        visiting.discard(slug)
        seen.add(slug)
        order.append(slug)

    for slug in graph.nodes:
        visit(slug)
    return {slug: i for i, slug in enumerate(order)}


def finalize_queue(
    required_queue: list[str],
    accepted_soft_slugs: list[str],
    *,
    graph: DependencyGraph,
) -> list[str]:
    """Unisce coda required e soft accettate, deduplicata e ordinata.

    Le ``required`` restano per prime nel loro ordine topologico; le soft
    accettate non già presenti vengono accodate (riordinate topologicamente tra
    loro per coerenza). Lo slug duplicato compare una sola volta.

    Args:
        required_queue: Coda delle ``required`` (già in ordine topologico).
        accepted_soft_slugs: Slug delle proposte soft accettate dall'utente.
        graph: Grafo completo (per l'ordinamento topologico delle soft).

    Returns:
        Lista di slug deduplicata: required prima, poi soft accettate.
    """
    result: list[str] = []
    seen: set[str] = set()
    for slug in required_queue:
        if slug not in seen:
            result.append(slug)
            seen.add(slug)

    topo = _topo_index(graph)
    soft = [s for s in dict.fromkeys(accepted_soft_slugs) if s not in seen]
    soft.sort(key=lambda s: topo.get(s, len(topo)))
    for slug in soft:
        result.append(slug)
        seen.add(slug)
    return result
