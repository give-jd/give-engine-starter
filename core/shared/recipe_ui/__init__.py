"""Helper UI condivisi per le app ricetta Streamlit (Fase 3, spec §4.7).

Espone la barra dipendenze runtime. La logica pura (calcolo degli elementi) vive
in ``deps_bar_logic``; il rendering ``st.*`` in ``dependency_bar`` con import lazy
di Streamlit, così il package resta importabile anche senza Streamlit installato.
"""

from __future__ import annotations

__all__ = ["deps_bar_logic", "dependency_bar"]
