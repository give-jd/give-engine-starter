"""Base parser API per bollette PDF."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ParsedBolletta:
    """Output normalizzato da qualsiasi parser."""
    fornitore: Optional[str] = None
    tipo: Optional[str] = None
    pod_pdr: Optional[str] = None
    intestatario: Optional[str] = None
    periodo_inizio: Optional[str] = None
    periodo_fine: Optional[str] = None
    consumo_qta: Optional[float] = None
    consumo_unita: Optional[str] = None
    # Letture contatore assolute (da DETTAGLIO LETTURE), per integrazione letture-contatori.
    lettura_prec: Optional[float] = None
    lettura_prec_data: Optional[str] = None
    lettura_att: Optional[float] = None
    lettura_att_data: Optional[str] = None
    importo_totale: Optional[float] = None
    importo_imponibile: Optional[float] = None
    iva: Optional[float] = None
    scadenza: Optional[str] = None
    parser_usato: str = "unknown"
    confidence: float = 0.0
    raw_text: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class BaseBollettaParser:
    """Interfaccia parser per ogni fornitore italiano."""

    NAME: str = "base"
    FORNITORE_DISPLAY: str = "Sconosciuto"
    TIPO: Optional[str] = None

    def match(self, text: str) -> bool:
        """Ritorna True se il testo PDF sembra una bolletta di questo vendor."""
        raise NotImplementedError

    def parse(self, text: str) -> ParsedBolletta:
        """Estrae i campi normalizzati."""
        raise NotImplementedError(f"Parser {self.NAME} non ancora implementato")
