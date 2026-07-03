"""Resolver delle dipendenze tra ricette: parse, grafo, risoluzione, validazione."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.shared.deps.exceptions import DependencyCycle
from core.shared.deps.models import Dependency, DepKind, RecipeNode

_KINDS: tuple[DepKind, ...] = ("required", "recommended", "optional")


@dataclass
class DependencyGraph:
    """Grafo di tutte le ricette indicizzate per slug."""

    nodes: dict[str, RecipeNode] = field(default_factory=dict)


def _parse_deps(block: dict | None) -> list[Dependency]:
    deps: list[Dependency] = []
    if not block:
        return deps
    for kind in _KINDS:
        for item in block.get(kind, []) or []:
            deps.append(
                Dependency(
                    slug=str(item["slug"]),
                    kind=kind,
                    min_version=(str(item["min_version"]) if item.get("min_version") else None),
                    reason=str(item.get("reason", "")),
                )
            )
    return deps


def load_graph(recipes_dir: Path) -> DependencyGraph:
    """Carica tutti i ``recipe.yaml`` sotto ``recipes_dir`` in un grafo.

    Args:
        recipes_dir: Directory che contiene una sottocartella per ricetta.

    Returns:
        Il grafo con i nodi indicizzati per slug.
    """
    graph = DependencyGraph()
    for yaml_path in sorted(recipes_dir.glob("*/recipe.yaml")):
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        slug = str(data.get("id") or yaml_path.parent.name)
        node = RecipeNode(
            slug=slug,
            tier=str(data.get("tier", "starter")),
            version=str(data.get("versione", "1.0.0")),
            deps=_parse_deps(data.get("dependencies")),
        )
        graph.nodes[slug] = node
    return graph


def resolve_required(
    slug: str, *, graph: DependencyGraph, installed: set[str]
) -> list[str]:
    """Risolve la chiusura transitiva delle dipendenze ``required`` di ``slug``.

    Args:
        slug: Ricetta da installare.
        graph: Grafo completo delle ricette.
        installed: Slug già installati (esclusi dal risultato).

    Returns:
        Lista di slug in ordine topologico (le dipendenze prima dei dipendenti),
        escluso ``slug`` stesso e quelle già installate.

    Raises:
        DependencyCycle: Se esiste un ciclo nelle dipendenze ``required``.
    """
    ordered: list[str] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node_slug: str) -> None:
        if node_slug in done:
            return
        if node_slug in visiting:
            raise DependencyCycle(f"Ciclo nelle dipendenze required attorno a '{node_slug}'")
        visiting.add(node_slug)
        node = graph.nodes.get(node_slug)
        if node is not None:
            for dep in node.required:
                visit(dep.slug)
        visiting.discard(node_slug)
        done.add(node_slug)
        if node is not None and node_slug != slug and node_slug not in installed:
            ordered.append(node_slug)

    visit(slug)
    return ordered


def proposals(
    slug: str, *, graph: DependencyGraph, installed: set[str]
) -> list[Dependency]:
    """Dipendenze soft (recommended + optional) non ancora installate.

    Args:
        slug: Ricetta in installazione.
        graph: Grafo completo.
        installed: Slug già installati.

    Returns:
        Lista di Dependency recommended (prima) e optional, escluse le installate.
    """
    node = graph.nodes.get(slug)
    if node is None:
        return []
    soft = [*node.recommended, *node.optional]
    return [d for d in soft if d.slug not in installed]


def companions(slug: str, *, graph: DependencyGraph) -> list[str]:
    """Alias derivato per retro-compat: slug recommended + optional.

    Args:
        slug: Ricetta.
        graph: Grafo completo.

    Returns:
        Lista di slug (recommended seguiti da optional).
    """
    node = graph.nodes.get(slug)
    if node is None:
        return []
    return [d.slug for d in (*node.recommended, *node.optional)]


_TIER_RANK = {"starter": 0, "catalog": 1}


def _is_semver(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def _node_dep_errors(slug: str, node: RecipeNode, graph: DependencyGraph) -> list[str]:
    """Errors for a single node's deps: missing slug, bad semver, tier violation."""
    errors: list[str] = []
    for dep in node.deps:
        target = graph.nodes.get(dep.slug)
        if target is None:
            errors.append(f"Ricetta '{slug}': dipendenza '{dep.slug}' inesistente nel catalogo.")
            continue
        if dep.min_version is not None and not _is_semver(dep.min_version):
            errors.append(
                f"Ricetta '{slug}': min_version '{dep.min_version}' per '{dep.slug}' "
                "non è semver X.Y.Z."
            )
        if dep.kind == "required" and _TIER_RANK.get(target.tier, 0) > _TIER_RANK.get(node.tier, 0):
            errors.append(
                f"Ricetta '{slug}' (tier {node.tier}): dipendenza required "
                f"'{dep.slug}' ha tier superiore ({target.tier}) — violazione tier."
            )
    return errors


def _required_cycle_errors(graph: DependencyGraph) -> list[str]:
    """Errors for cycles along the ``required`` edges (DFS over the whole graph)."""
    errors: list[str] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node_slug: str, stack: tuple[str, ...]) -> None:
        if node_slug in done:
            return
        if node_slug in visiting:
            errors.append(f"Ciclo nelle dipendenze required: {' -> '.join((*stack, node_slug))}.")
            return
        visiting.add(node_slug)
        node = graph.nodes.get(node_slug)
        if node is not None:
            for dep in node.required:
                visit(dep.slug, (*stack, node_slug))
        visiting.discard(node_slug)
        done.add(node_slug)

    for slug in graph.nodes:
        visit(slug, ())
    return errors


def validate(graph: DependencyGraph) -> list[str]:
    """Valida il grafo. Restituisce la lista di messaggi d'errore (vuota se ok).

    Controlla: slug dipendenza inesistente, ciclo sulle ``required``,
    tier-violation (una ``required`` non può avere tier superiore alla ricetta),
    ``min_version`` malformata.

    Args:
        graph: Grafo completo.

    Returns:
        Lista di stringhe d'errore in italiano (vuota = grafo valido).
    """
    errors: list[str] = []
    for slug, node in graph.nodes.items():
        errors.extend(_node_dep_errors(slug, node, graph))
    errors.extend(_required_cycle_errors(graph))
    return errors
