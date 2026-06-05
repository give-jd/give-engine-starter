"""Parsers package — auto-detect fornitore + fallback euristico."""

from __future__ import annotations

from typing import List
from .base import BaseBollettaParser, ParsedBolletta
from . import enel, eni, edison, a2a, iren, vodafone, tim, fastweb, hera, acea, agn, _fallback

ALL_PARSERS: List[type[BaseBollettaParser]] = [
    enel.EnelParser,
    eni.EniParser,
    edison.EdisonParser,
    a2a.A2AParser,
    iren.IrenParser,
    hera.HeraParser,
    acea.AceaParser,
    agn.AgnParser,
    vodafone.VodafoneParser,
    tim.TimParser,
    fastweb.FastwebParser,
]
FALLBACK = _fallback.FallbackParser


def dispatch(text: str) -> ParsedBolletta:
    """Trova il parser vendor + estrae. Cade su fallback se nessuno matcha."""
    for cls in ALL_PARSERS:
        try:
            p = cls()
            if p.match(text):
                return p.parse(text)
        except NotImplementedError:
            continue
        except Exception as e:
            print(f"[parser.{cls.__name__}] err: {e}")
            continue
    return FALLBACK().parse(text)
