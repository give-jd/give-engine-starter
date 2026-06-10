"""Base parser API per calendari rifiuti comunali (PDF/testo).

Modello imitato da ``bollette-watcher/parsers/base.py``: dataclass di output
normalizzato + classe base con ``match``/``parse``. Qui l'output e' una lista
di ricorrenze (frazione + regola), che l'utente verifica prima di salvare.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RicorrenzaParsed:
    """Una ricorrenza estratta dal calendario (da verificare prima del salvataggio).

    Rispecchia i campi di ``ricorrenze`` in ``schema.sql``.
    """
    frazione: str
    tipo: str = "settimanale"  # settimanale|quindicinale|mensile|lista_date
    giorni_settimana: str | None = None  # CSV ISO "1,4"
    settimane_alterne: int = 0
    giorno_mese: int | None = None
    date_extra: str | None = None  # CSV ISO
    valido_da: str | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedCalendar:
    """Output normalizzato di un parser di calendario.

    Attributes:
        comune: Nome comune se rilevato.
        ricorrenze: Lista di ``RicorrenzaParsed``.
        parser_usato: Nome del parser che ha prodotto l'output.
        confidence: Stima 0..1 di affidabilita'.
        raw_text: Testo grezzo di partenza (debug).
    """
    comune: str | None = None
    ricorrenze: list[RicorrenzaParsed] = field(default_factory=list)
    parser_usato: str = "unknown"
    confidence: float = 0.0
    raw_text: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ricorrenze"] = [
            r.to_dict() if hasattr(r, "to_dict") else r for r in self.ricorrenze
        ]
        return d


class BaseCalendarParser:
    """Interfaccia parser per un formato di calendario comunale."""

    NAME: str = "base"
    COMUNE_DISPLAY: str | None = None

    def match(self, text: str) -> bool:
        """Ritorna True se il testo sembra del formato gestito da questo parser."""
        raise NotImplementedError

    def parse(self, text: str) -> ParsedCalendar:
        """Estrae le ricorrenze normalizzate dal testo."""
        raise NotImplementedError(f"Parser {self.NAME} non ancora implementato")
