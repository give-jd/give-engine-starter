"""Parser generico best-effort: estrae giorni/date da testo libero.

Ultima risorsa testuale prima del fallback manuale. Cerca, riga per riga,
una frazione nota seguita da giorni della settimana o date ISO/IT, senza
pretendere un formato specifico. Confidence sempre bassa: l'output va
verificato dall'utente.

L'estrazione del testo dal PDF usa ``pdfplumber`` (import lazy in ``estrai_testo``).
"""

from __future__ import annotations

import re

from .base import BaseCalendarParser, ParsedCalendar, RicorrenzaParsed

_GIORNI = {
    "lunedi": 1, "lun": 1, "martedi": 2, "mar": 2, "mercoledi": 3, "mer": 3,
    "giovedi": 4, "gio": 4, "venerdi": 5, "ven": 5, "sabato": 6, "sab": 6,
    "domenica": 7, "dom": 7,
}

# frazioni note (radici) per ancorare le righe
_FRAZIONI_KW = [
    "umido", "organico", "indifferenziat", "secco", "carta", "cartone",
    "plastica", "lattine", "vetro", "verde", "sfalci", "raee", "ingombrant",
    "farmac", "pile",
]

_RX_DATA_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_RX_DATA_IT = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b")


def _normalizza(s: str) -> str:
    return (
        s.lower()
        .replace("à", "a").replace("è", "e").replace("é", "e")
        .replace("ì", "i").replace("ò", "o").replace("ù", "u").replace("'", "")
    )


def estrai_testo(pdf_bytes: bytes) -> str | None:
    """Estrae testo da un PDF con ``pdfplumber`` (import lazy).

    Args:
        pdf_bytes: Contenuto binario del PDF.

    Returns:
        Il testo concatenato, oppure ``None`` se ``pdfplumber`` non e' installato
        o l'estrazione fallisce (es. PDF immagine senza testo embedded).
    """
    try:
        import io

        import pdfplumber  # type: ignore
    except ImportError:
        return None
    try:
        parti: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt:
                    parti.append(txt)
        joined = "\n".join(parti)
        return joined or None
    except Exception:
        return None


def _giorni_in(testo_norm: str) -> list[int]:
    out: list[int] = []
    for token in re.split(r"[,/]|\be\b|\s+", testo_norm):
        if token in _GIORNI and _GIORNI[token] not in out:
            out.append(_GIORNI[token])
    return sorted(out)


def _date_iso_in(riga: str) -> list[str]:
    out = list(_RX_DATA_ISO.findall(riga))
    for g, m, y in _RX_DATA_IT.findall(riga):
        anno = int(y) + 2000 if len(y) == 2 else int(y)
        out.append(f"{anno:04d}-{int(m):02d}-{int(g):02d}")
    return out


class GenericTextParser(BaseCalendarParser):
    """Estrattore euristico best-effort da testo libero."""

    NAME = "generic_text"

    def match(self, text: str) -> bool:
        norm = _normalizza(text)
        ha_frazione = any(kw in norm for kw in _FRAZIONI_KW)
        tokens = set(re.split(r"\W+", norm))
        ha_giorno = any(g in tokens for g in _GIORNI)
        ha_data = bool(_RX_DATA_ISO.search(text) or _RX_DATA_IT.search(text))
        return ha_frazione and (ha_giorno or ha_data)

    def parse(self, text: str) -> ParsedCalendar:
        cal = ParsedCalendar(parser_usato=self.NAME, raw_text=text)
        for riga in text.splitlines():
            norm = _normalizza(riga)
            if not any(kw in norm for kw in _FRAZIONI_KW):
                continue
            frazione = riga.split(":")[0].strip() if ":" in riga else riga.strip()
            giorni = _giorni_in(norm)
            date_iso = _date_iso_in(riga)
            if giorni:
                cal.ricorrenze.append(RicorrenzaParsed(
                    frazione=frazione, tipo="settimanale",
                    giorni_settimana=",".join(str(g) for g in giorni),
                ))
            elif date_iso:
                cal.ricorrenze.append(RicorrenzaParsed(
                    frazione=frazione, tipo="lista_date",
                    date_extra=",".join(date_iso),
                ))
        cal.confidence = 0.3 if cal.ricorrenze else 0.0
        return cal
