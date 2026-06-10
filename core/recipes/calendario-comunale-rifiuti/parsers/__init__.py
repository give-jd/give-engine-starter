"""Parsers package calendario-comunale-rifiuti.

API pubblica: ``detect_parser``/``dispatch`` (registry), dataclass di output
(``ParsedCalendar``, ``RicorrenzaParsed``) ed ``estrai_testo`` (pdfplumber lazy).
I moduli opt-in (OCR, AI BYOK) sono import-lazy e non vengono caricati qui.
"""

from __future__ import annotations

from ._generic_text import estrai_testo
from .base import BaseCalendarParser, ParsedCalendar, RicorrenzaParsed
from .registry import ALL_PARSERS, detect_parser, dispatch

__all__ = [
    "BaseCalendarParser",
    "ParsedCalendar",
    "RicorrenzaParsed",
    "detect_parser",
    "dispatch",
    "estrai_testo",
    "ALL_PARSERS",
]
