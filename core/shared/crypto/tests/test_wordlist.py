"""Verifica integrità wordlist BIP-39 italiana 2048 termini.

Test eseguiti al load del modulo crypto:
- Wordlist file exists at WORDLIST_PATH
- 2048 termini esatti (line count)
- SHA-256 match WORDLIST_IT_SHA256 (tamper detection)
- Tutte parole UTF-8 NFC lowercase, no duplicati
- Ordine alfabetico

Eseguito Pre-Q3 W2 retrofit (29 mag 2026). Wordlist scaricata da
bitcoin/bips master/bip-0039/italian.txt canonical.
"""

from __future__ import annotations

import hashlib
import unicodedata

from core.shared.crypto.recovery_bip39 import (
    PHRASE_LEN,
    WORDLIST_IT_SHA256,
    WORDLIST_PATH,
)


def _load_wordlist() -> list[str]:
    """Helper: load wordlist + split per linee."""
    text = WORDLIST_PATH.read_text(encoding="utf-8")
    # Split su newline, rimuovi linee vuote
    return [line.strip() for line in text.splitlines() if line.strip()]


class TestWordlistFile:
    """Verifica file wordlist presente e ben formato."""

    def test_wordlist_path_exists(self):
        assert WORDLIST_PATH.exists(), f"Wordlist non trovata: {WORDLIST_PATH}"

    def test_wordlist_count_2048(self):
        words = _load_wordlist()
        assert len(words) == 2048, f"Atteso 2048 termini, trovati {len(words)}"

    def test_wordlist_sha256_matches(self):
        """Tamper detection: SHA-256 wordlist deve match constante dichiarata."""
        raw_bytes = WORDLIST_PATH.read_bytes()
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        assert actual_hash == WORDLIST_IT_SHA256, (
            f"Wordlist tampered: expected {WORDLIST_IT_SHA256}, got {actual_hash}"
        )


class TestWordlistContent:
    """Verifica contenuto wordlist (no duplicati, ordine, encoding)."""

    def test_no_duplicates(self):
        words = _load_wordlist()
        assert len(set(words)) == len(words), "Wordlist contiene duplicati"

    def test_all_lowercase(self):
        words = _load_wordlist()
        for w in words:
            assert w == w.lower(), f"Parola non lowercase: {w!r}"

    def test_all_utf8_nfc(self):
        """Tutte le parole devono essere UTF-8 NFC normalizzate."""
        words = _load_wordlist()
        for w in words:
            assert w == unicodedata.normalize("NFC", w), f"Non NFC: {w!r}"

    def test_alphabetical_order(self):
        """BIP-39 wordlist deve essere ordinata alfabeticamente."""
        words = _load_wordlist()
        sorted_words = sorted(words)
        assert words == sorted_words, "Wordlist non in ordine alfabetico"

    def test_min_length_3(self):
        """BIP-39 spec: min 3 char per parola."""
        words = _load_wordlist()
        for w in words:
            assert len(w) >= 3, f"Parola < 3 char: {w!r}"

    def test_first_word_abaco(self):
        """Prima parola wordlist IT canonical."""
        words = _load_wordlist()
        assert words[0] == "abaco"

    def test_last_word_zuppa(self):
        """Ultima parola wordlist IT canonical."""
        words = _load_wordlist()
        assert words[-1] == "zuppa"


class TestBip39Constants:
    """Verifica costanti BIP-39 standard."""

    def test_phrase_len_12(self):
        assert PHRASE_LEN == 12

    def test_wordlist_indexable_11_bit(self):
        """2048 = 2^11. Indice 11-bit BIP-39 standard."""
        words = _load_wordlist()
        assert len(words) == 2**11
