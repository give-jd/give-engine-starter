"""Logica pura della barra dipendenze runtime (Fase 3, spec §4.7).

Calcola gli elementi della barra "Apri/Aggiungi" che la ricetta installata
mostra per le proprie dipendenze. Funzione pura, senza Streamlit: il rendering
``st.*`` vive in ``dependency_bar.render`` e consuma questo output.
"""

from __future__ import annotations

from core.shared.deps.resolver import DependencyGraph

_KIND_ORDER = ("required", "recommended", "optional")


def bar_items(
    recipe_id: str,
    *,
    graph: DependencyGraph,
    installed: set[str],
) -> list[dict]:
    """Elementi della barra dipendenze per ``recipe_id``.

    Per ogni dipendenza (required, poi recommended, poi optional) ritorna un dict
    con stato installato e label/href pronti per il rendering.

    Args:
        recipe_id: Id della ricetta che mostra la barra.
        graph: Grafo completo delle ricette.
        installed: Slug attualmente installati.

    Returns:
        Lista di dict ``{"slug","nome","kind","installed","label","href_kind"}``,
        ordinata required → recommended → optional. Vuota se la ricetta non ha
        dipendenze o non è nel grafo.
    """
    node = graph.nodes.get(recipe_id)
    if node is None:
        return []

    by_kind = {
        "required": node.required,
        "recommended": node.recommended,
        "optional": node.optional,
    }

    items: list[dict] = []
    for kind in _KIND_ORDER:
        for dep in by_kind[kind]:
            slug = dep.slug
            dep_node = graph.nodes.get(slug)
            nome = dep_node.slug if dep_node is not None else slug
            is_installed = slug in installed
            if is_installed:
                label = f"🔗 Apri {nome}"
                href_kind = "open"
            else:
                label = f"➕ Aggiungi {nome}"
                href_kind = "add"
            items.append(
                {
                    "slug": slug,
                    "nome": nome,
                    "kind": kind,
                    "installed": is_installed,
                    "label": label,
                    "href_kind": href_kind,
                }
            )
    return items
