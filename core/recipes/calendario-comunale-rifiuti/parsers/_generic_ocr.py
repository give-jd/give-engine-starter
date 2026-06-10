"""OCR opt-in per calendari rifiuti in PDF-immagine (Tesseract).

Modulo NON bloccante e import-lazy: se ``pytesseract`` + ``pdf2image`` (o il
binario Tesseract) non sono installati, ``is_available`` ritorna False e
``extract_text`` ritorna None. La ricetta funziona senza OCR (fallback manuale).

Limiti onesti: OCR italiano ~85% su scansioni pulite, peggiora su PDF storti.
"""

from __future__ import annotations


def is_available() -> bool:
    """True se il backend OCR (pytesseract + pdf2image + Tesseract) e' disponibile."""
    try:
        import pdf2image  # noqa: F401
        import pytesseract
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text(pdf_bytes: bytes, lang: str = "ita") -> str | None:
    """Estrae testo da un PDF scansionato via OCR Tesseract.

    Args:
        pdf_bytes: Contenuto binario del PDF.
        lang: Language pack Tesseract (default ``ita``).

    Returns:
        Il testo OCR, oppure ``None`` se il backend non e' disponibile o l'OCR fallisce.
    """
    if not is_available():
        return None
    try:
        import pdf2image
        import pytesseract

        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
        if not images:
            return None
        parti = [pytesseract.image_to_string(img, lang=lang) for img in images]
        joined = "\n".join(p for p in parti if p)
        return joined or None
    except Exception:
        return None
