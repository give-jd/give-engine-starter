"""Barra dipendenze runtime per le app ricetta Streamlit (Fase 3, spec §4.7, D3).

La ricetta installata mostra in cima alla pagina una riga di link verso le sue
dipendenze: "🔗 Apri <Nome>" se installata (via launcher Cabina ``/open/<slug>``),
"➕ Aggiungi <Nome>" altrimenti (verso la Cabina).

Streamlit è importato in modo LAZY dentro ``render`` così questo modulo resta
importabile senza Streamlit (la logica testabile vive in ``deps_bar_logic``).
"""

from __future__ import annotations

import os
from pathlib import Path

from core.shared.recipe_ui.deps_bar_logic import bar_items

# Default: la Cabina di Regia gira sulla porta 5000 (vedi core/orchestrator.py
# DEFAULT_PORT). All'avvio l'orchestrator scrive l'URL effettivo in prefs.
_DEFAULT_CABINA_URL = "http://localhost:5000"

# Directory delle ricette nel monorepo installato (core/recipes/).
_RECIPES_DIR = Path(__file__).resolve().parents[2] / "recipes"


def cabina_url() -> str:
    """URL della Cabina di Regia, da prefs o env, con fallback al default.

    Returns:
        L'URL base della Cabina (es. ``http://localhost:5000``), senza slash finale.
    """
    url = None
    try:
        from core import system as _sys

        url = _sys.get_pref("cabina_url", None)
    except Exception:
        url = None
    if not url:
        url = os.environ.get("GIVENGINE_CABINA_URL", _DEFAULT_CABINA_URL)
    return str(url).rstrip("/")


def _load_context(recipe_id: str, graph, installed):
    """Carica graph/installed se non forniti. Degrada a None su errore."""
    if graph is None:
        try:
            from core.shared.deps.resolver import load_graph

            graph = load_graph(_RECIPES_DIR)
        except Exception:
            return None, None
    if installed is None:
        try:
            from core import installed_registry

            installed = {
                str(r.get("slug"))
                for r in installed_registry.list_installed()
                if r.get("slug")
            }
        except Exception:
            installed = set()
    return graph, installed


def render(recipe_id: str, *, graph=None, installed=None) -> None:
    """Rende la barra dipendenze per ``recipe_id`` (no-op se nulla da mostrare).

    Args:
        recipe_id: Id della ricetta corrente.
        graph: Grafo dipendenze già caricato (altrimenti caricato da disco).
        installed: Set degli slug installati (altrimenti dal registro installati).

    Note:
        Degrada silenziosamente: se Streamlit non è disponibile o il caricamento
        del contesto fallisce, ritorna senza rompere l'app ricetta.
    """
    graph, installed = _load_context(recipe_id, graph, installed)
    if graph is None:
        return

    items = bar_items(recipe_id, graph=graph, installed=installed or set())
    if not items:
        return

    try:
        import streamlit as st
    except ImportError:
        return

    base = cabina_url()
    links: list[str] = []
    for item in items:
        if item["href_kind"] == "open":
            href = f"{base}/open/{item['slug']}"
        else:
            href = base
        links.append(f"[{item['label']}]({href})")

    st.markdown(" &nbsp;·&nbsp; ".join(links))
