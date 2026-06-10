"""Logica pura del launcher della Cabina (Fase 3, spec §4.7, D3).

Decide cosa fare quando si chiede di aprire una ricetta via ``GET /open/{slug}``.
Funzione pura, senza FastAPI: prende callback per stato installato/porta/copertura
licenza e ritorna un'azione dichiarativa. Il wiring HTTP nell'orchestrator resta
sottile e traduce l'azione in redirect/spawn.
"""

from __future__ import annotations

from collections.abc import Callable


def decide_open(
    slug: str,
    *,
    installed: set[str],
    get_port: Callable[[str], int | None],
    is_covered: Callable[[str], bool],
) -> dict:
    """Decide l'azione per l'apertura di ``slug`` dalla Cabina.

    Args:
        slug: Id della ricetta da aprire.
        installed: Set degli slug attualmente installati.
        get_port: Callback slug -> porta locale registrata (o None se ignota).
        is_covered: Callback slug -> True se coperta dalla licenza utente.

    Returns:
        Un dict azione:
          - non installata: ``{"action": "install_redirect", "slug": slug}``
          - non coperta:    ``{"action": "pricing_redirect"}``
          - altrimenti:     ``{"action": "open", "slug": slug, "port": <int|None>}``
            (``port`` None → l'orchestrator dovrà spawnare e scoprire la porta).
    """
    if slug not in installed:
        return {"action": "install_redirect", "slug": slug}
    if not is_covered(slug):
        return {"action": "pricing_redirect"}
    return {"action": "open", "slug": slug, "port": get_port(slug)}
