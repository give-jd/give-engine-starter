"""Parser fallback OCR Tesseract per PDF scansionati.

Lazy import: se `pytesseract` + `pdf2image` non installati o Tesseract OS
non disponibile, fallback graceful (returns None).

Pattern coerente con _fallback.py regex-based per PDF estraibili.
OCR è ULTIMA risorsa per PDF totalmente scansionati (no testo embedded).

Limite onesto v1.0 (documentato in UI):
- OCR Tesseract italiano = ~85% accuracy su PDF bollette standard
- Scarsa accuracy su scansioni storte/poco contrasto
- Tempo elaborazione: ~5-15s per pagina
"""

from __future__ import annotations


def is_available() -> bool:
    """Verifica se OCR backend (pytesseract + pdf2image) è installato.

    Lazy import — no ImportError se libs missing.
    """
    try:
        import pytesseract  # noqa: F401
        import pdf2image  # noqa: F401
    except ImportError:
        return False
    # Verifica Tesseract binary
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text(pdf_bytes: bytes, lang: str = "ita") -> str | None:
    """Estrae testo da PDF scansionato via OCR Tesseract.

    Args:
        pdf_bytes: PDF binary content.
        lang: Tesseract language pack (default "ita" italiano).

    Returns:
        Testo estratto, o None se OCR backend non disponibile o errore.
    """
    if not is_available():
        return None
    try:
        import pdf2image
        import pytesseract

        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
        if not images:
            return None
        texts: list[str] = []
        for img in images:
            txt = pytesseract.image_to_string(img, lang=lang)
            if txt:
                texts.append(txt)
        joined = "\n".join(texts)
        return joined or None
    except Exception:
        # OCR failure ≠ crash applicazione — graceful degradation
        return None
