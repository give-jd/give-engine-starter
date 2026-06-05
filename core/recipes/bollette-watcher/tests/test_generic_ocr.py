"""Tests _generic_ocr Tesseract fallback (lazy import + graceful fallback)."""

from __future__ import annotations

import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parents[1]
if str(RECIPE_DIR) not in sys.path:
    sys.path.insert(0, str(RECIPE_DIR))

from parsers import _generic_ocr  # noqa: E402


class TestAvailability:
    def test_is_available_returns_bool(self):
        """is_available returns bool (no exception se libs missing)."""
        result = _generic_ocr.is_available()
        assert isinstance(result, bool)


class TestExtractText:
    def test_extract_returns_none_if_not_available(self):
        """Senza Tesseract installato, extract returns None (no crash)."""
        if _generic_ocr.is_available():
            return
        result = _generic_ocr.extract_text(b"fake-pdf-bytes")
        assert result is None

    def test_extract_handles_invalid_pdf_gracefully(self):
        """PDF bytes invalidi → None, no exception."""
        result = _generic_ocr.extract_text(b"not a valid pdf at all")
        assert result is None or isinstance(result, str)
