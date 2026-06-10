"""Estrazione AI BYOK (opt-in, default OFF) — import-lazy, mai bloccante.

Usa la chiave Anthropic dell'utente (BYOK) per estrarre ricorrenze da testo
ostico o classificare una foto di un rifiuto. Se ``anthropic`` non e' installato
o la chiave manca, le funzioni degradano (ritornano None) senza sollevare: la
ricetta resta pienamente usabile senza AI.

Punto cardine: Gi.Ve resta fuori dal flusso; la chiamata esterna esiste solo
se l'utente attiva l'AI con la PROPRIA chiave. In v1 questo modulo e' uno stub
NON bloccante (nessuna chiamata di rete); l'integrazione reale e' demandata a v1.1.
"""

from __future__ import annotations


def is_available() -> bool:
    """True se l'SDK ``anthropic`` e' importabile (la chiave la passa il chiamante)."""
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def estrai_ricorrenze(text: str, api_key: str | None) -> list[dict] | None:
    """Estrae ricorrenze da testo libero via modello Anthropic (BYOK).

    Args:
        text: Testo del calendario.
        api_key: Chiave Anthropic dell'utente. Se assente -> None.

    Returns:
        Lista di dict ricorrenza (da verificare), ``None`` se AI non disponibile,
        chiave assente o errore. Mai solleva.
    """
    if not api_key or not is_available():
        return None
    try:
        # v1: stub non bloccante, nessuna chiamata di rete. Implementazione AI in v1.1.
        return None
    except Exception:
        return None


def classifica_foto(image_bytes: bytes, api_key: str | None) -> str | None:
    """Classifica il materiale di un rifiuto da una foto (BYOK).

    Args:
        image_bytes: Immagine (es. da ``st.camera_input``).
        api_key: Chiave Anthropic dell'utente.

    Returns:
        Etichetta materiale suggerita (da verificare nel regolamento), oppure
        ``None`` se AI non disponibile/chiave assente/errore. Mai solleva.
    """
    if not api_key or not is_available():
        return None
    try:
        # v1: stub non bloccante. Implementazione visione in v1.1.
        return None
    except Exception:
        return None
