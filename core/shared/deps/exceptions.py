"""Eccezioni del resolver dipendenze."""

from __future__ import annotations


class DependencyError(Exception):
    """Errore generico di risoluzione dipendenze."""


class DependencyCycle(DependencyError):
    """Ciclo rilevato nel grafo delle dipendenze `required`."""


class TierViolation(DependencyError):
    """Una dipendenza `required` ha tier superiore alla ricetta che la richiede."""


class MissingDependency(DependencyError):
    """Lo slug di una dipendenza non esiste nel catalogo."""


class VersionConflict(DependencyError):
    """`min_version` malformata o non soddisfacibile."""
