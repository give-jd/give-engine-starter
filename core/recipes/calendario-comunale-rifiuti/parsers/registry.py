"""Registry parser calendario: detect_parser + dispatch.

Ordine di priorita': adapter specifici (es. ``EsempioSettimanaleParser``) prima,
``GenericTextParser`` best-effort come fallback testuale. Nessun match -> None
(l'app ricade sull'inserimento manuale guidato).
"""

from __future__ import annotations

from ._esempio_settimanale import EsempioSettimanaleParser
from ._generic_text import GenericTextParser
from .base import BaseCalendarParser, ParsedCalendar

# adapter specifici prima, generico per ultimo
ALL_PARSERS: list[type[BaseCalendarParser]] = [
    EsempioSettimanaleParser,
    GenericTextParser,
]


def detect_parser(text: str) -> BaseCalendarParser | None:
    """Trova il primo parser che riconosce il testo.

    Args:
        text: Testo estratto dal calendario.

    Returns:
        Un'istanza del parser che matcha, oppure ``None`` se nessuno riconosce
        il formato (-> fallback all'inserimento manuale).
    """
    if not (text or "").strip():
        return None
    for cls in ALL_PARSERS:
        try:
            p = cls()
            if p.match(text):
                return p
        except NotImplementedError:
            continue
        except Exception:
            continue
    return None


def dispatch(text: str) -> ParsedCalendar | None:
    """Rileva il parser ed estrae le ricorrenze.

    Args:
        text: Testo estratto dal calendario.

    Returns:
        Il ``ParsedCalendar`` prodotto, oppure ``None`` se nessun parser matcha.
    """
    parser = detect_parser(text)
    if parser is None:
        return None
    return parser.parse(text)
