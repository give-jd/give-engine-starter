"""Tipi dati del grafo dipendenze."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DepKind = Literal["required", "recommended", "optional"]


@dataclass(frozen=True)
class Dependency:
    """Una dipendenza dichiarata da una ricetta.

    Args:
        slug: Id della ricetta dipendenza.
        kind: Livello della dipendenza.
        min_version: Versione minima richiesta (semver "X.Y.Z") o None.
        reason: Spiegazione in italiano del perché serve.
    """

    slug: str
    kind: DepKind
    min_version: str | None
    reason: str


@dataclass(frozen=True)
class RecipeNode:
    """Una ricetta nel grafo, con le sue dipendenze.

    Args:
        slug: Id della ricetta.
        tier: "starter" | "catalog".
        version: Versione della ricetta (semver).
        deps: Tutte le dipendenze dichiarate, di qualunque kind.
    """

    slug: str
    tier: str
    version: str
    deps: list[Dependency] = field(default_factory=list)

    def _by_kind(self, kind: DepKind) -> list[Dependency]:
        return [d for d in self.deps if d.kind == kind]

    @property
    def required(self) -> list[Dependency]:
        return self._by_kind("required")

    @property
    def recommended(self) -> list[Dependency]:
        return self._by_kind("recommended")

    @property
    def optional(self) -> list[Dependency]:
        return self._by_kind("optional")
