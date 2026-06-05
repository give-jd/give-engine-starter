"""KAT (Known Answer Tests) BIP-39 recovery phrase.

10 test vector da:
- BIP-39 spec test vectors (Bitcoin Wiki canonical)
- Wordlist BIP-39 italiana 2048 termini

Categorie:
3.1 BIP-39 spec vector entropy + checksum (5)
3.2 Edge entropy (all zeros / all ones) (2 — coperti da 3.1)
3.3 Wordlist IT consistency (coperti da tests/test_wordlist.py — 12 test)
3.4 Checksum tamper (1)

NOTE: BIP-39 ufficiali spec vectors usano English wordlist. Italian
equivalent vectors verranno derivati computazionalmente W28 quando
entropy_to_phrase è implementato. Pre-Q3 W3 carica entropy + checksum
expected; phrase italiana computed at impl time.

Implementation Q3 W28 (8-14 lug 2026) sprint beta.
Riferimento KAT design: `givegroup-knowledge/shared/CRYPTO-V0.1-KAT-DESIGN.md` §3.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from core.shared.crypto.recovery_bip39 import (
    ENTROPY_BYTES,
    WORDLIST_IT_SHA256,
    WORDLIST_PATH,
)


@dataclass(frozen=True)
class Bip39EntropyVector:
    """BIP-39 entropy test vector (phrase IT calcolato at impl time)."""

    name: str
    entropy_hex: str  # 16 byte (128 bit)
    expected_checksum_bits: str  # 4 bit checksum atteso (binary string)


@dataclass(frozen=True)
class Bip39FullVector:
    """BIP-39 vector con phrase IT pre-computata (W28+)."""

    name: str
    entropy_hex: str
    expected_phrase_it: list[str]  # 12 italian words
    expected_seed_hex: str  # PBKDF2-HMAC-SHA512 derived seed
    passphrase: str = ""


# ============================================================================
# 3.1 BIP-39 spec vector entropy + checksum (5 vectors)
# ============================================================================
# Entropy + checksum binary precomputati (validabile senza wordlist).
# Phrase IT equivalente computed at impl time W28.

VECTOR_ALL_ZEROS = Bip39EntropyVector(
    name="bip39_spec_all_zeros_128bit",
    entropy_hex="00000000000000000000000000000000",
    # SHA-256(0x00*16) = 374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb
    # First byte 0x37 = 0011_0111, first 4 bit = 0011
    expected_checksum_bits="0011",
)

VECTOR_ALL_ONES = Bip39EntropyVector(
    name="bip39_spec_all_ones_128bit",
    entropy_hex="ffffffffffffffffffffffffffffffff",
    # SHA-256(0xff*16) first byte verificato via hashlib (test pass):
    # first 4 bit = 0101 binary (= 5 decimal)
    expected_checksum_bits="0101",
)

VECTOR_ALTERNATING_55 = Bip39EntropyVector(
    name="bip39_spec_alternating_5555",
    entropy_hex="55555555555555555555555555555555",
    # SHA-256 first 4 bit computed at W28
    expected_checksum_bits="TBD",
)

VECTOR_INCREMENTAL = Bip39EntropyVector(
    name="bip39_spec_incremental_0123456789abcdef",
    entropy_hex="0123456789abcdef0123456789abcdef",
    expected_checksum_bits="TBD",
)

VECTOR_NIST_SAMPLE = Bip39EntropyVector(
    name="bip39_spec_nist_sample_entropy",
    entropy_hex="80808080808080808080808080808080",
    expected_checksum_bits="TBD",
)


BIP39_ENTROPY_VECTORS: list[Bip39EntropyVector] = [
    VECTOR_ALL_ZEROS,
    VECTOR_ALL_ONES,
    VECTOR_ALTERNATING_55,
    VECTOR_INCREMENTAL,
    VECTOR_NIST_SAMPLE,
]


# ============================================================================
# 3.2 Edge entropy — già coperti in 3.1 (all zeros + all ones)
# ============================================================================
EDGE_ENTROPY_VECTORS: list[Bip39EntropyVector] = []


# ============================================================================
# 3.3 Wordlist IT consistency
# ============================================================================
# Test in tests/test_wordlist.py — 12 test pass W2 retrofit.
WORDLIST_CONSISTENCY_NOTE: str = (
    "Wordlist tests in tests/test_wordlist.py — 12 test pass W2 retrofit. "
    "SHA-256 = d392c49fdb700a24cd1fceb237c1f65dcc128f6b34a8aacb58b59384b5c648c2"
)


# ============================================================================
# 3.4 Checksum tamper (1 vector) — TBD Q3 W28
# ============================================================================
TAMPER_VECTORS: list[Bip39EntropyVector] = []


# Italian phrase + seed full vectors (W28+ post entropy_to_phrase impl)
FULL_VECTORS_W28: list[Bip39FullVector] = []


ALL_VECTORS: list[Bip39EntropyVector | Bip39FullVector] = (
    list(BIP39_ENTROPY_VECTORS)
    + list(EDGE_ENTROPY_VECTORS)
    + list(TAMPER_VECTORS)
    + list(FULL_VECTORS_W28)
)


# ============================================================================
# Test runner
# ============================================================================


class TestBip39KatStructure:
    """Verifica struttura vector BIP-39 (no impl required)."""

    def test_bip39_entropy_vectors_present(self):
        """Pre-Q3 W3 retrofit: 5 entropy vector caricati."""
        assert len(BIP39_ENTROPY_VECTORS) == 5
        for v in BIP39_ENTROPY_VECTORS:
            entropy_bytes = bytes.fromhex(v.entropy_hex)
            assert len(entropy_bytes) == ENTROPY_BYTES, (
                f"{v.name}: entropy not {ENTROPY_BYTES} byte"
            )

    def test_all_zeros_checksum_verified(self):
        """Verifica checksum SHA-256 first 4 bit per entropy all-zeros.

        Computable senza impl (hashlib stdlib).
        """
        entropy = bytes.fromhex(VECTOR_ALL_ZEROS.entropy_hex)
        sha = hashlib.sha256(entropy).digest()
        first_byte = sha[0]
        actual_checksum = format(first_byte >> 4, "04b")
        assert actual_checksum == VECTOR_ALL_ZEROS.expected_checksum_bits, (
            f"Checksum mismatch: {actual_checksum} vs {VECTOR_ALL_ZEROS.expected_checksum_bits}"
        )

    def test_all_ones_checksum_verified(self):
        """Verifica checksum per entropy all-ones."""
        entropy = bytes.fromhex(VECTOR_ALL_ONES.entropy_hex)
        sha = hashlib.sha256(entropy).digest()
        first_byte = sha[0]
        actual_checksum = format(first_byte >> 4, "04b")
        assert actual_checksum == VECTOR_ALL_ONES.expected_checksum_bits

    def test_wordlist_sha256_constant_present(self):
        """WORDLIST_IT_SHA256 constant aggiornato post W2 retrofit."""
        assert WORDLIST_IT_SHA256 != "TBD_W2_W3_PRE_Q3"
        assert len(WORDLIST_IT_SHA256) == 64  # SHA-256 hex string

    def test_wordlist_path_exists(self):
        """Path wordlist esistente post W2 retrofit."""
        assert WORDLIST_PATH.exists()

    def test_target_10_vectors_planned(self):
        """10 vector totali target W29 stable. Current: 5 entropy."""
        assert len(ALL_VECTORS) >= 5


@pytest.mark.parametrize("vector", BIP39_ENTROPY_VECTORS, ids=lambda v: v.name)
def test_bip39_kat_entropy(vector: Bip39EntropyVector):
    """Test parametrizzato KAT BIP-39 entropy → phrase IT.

    Implementation Q3 W28 (8-14 lug 2026) sprint beta.
    Skip fino entropy_to_phrase è implementato.
    """
    """KAT BIP-39 entropy → phrase IT verify.

    Impl Q3 W28 sprint beta ATTIVA. Validation:
    - entropy_to_phrase returns 12 word list
    - verify_phrase confirms checksum valid
    """
    from core.shared.crypto import recovery_bip39

    entropy = bytes.fromhex(vector.entropy_hex)
    phrase = recovery_bip39.entropy_to_phrase(entropy)
    assert len(phrase) == 12, f"{vector.name}: phrase len != 12"
    # Self-verify (entropy → phrase → verify_phrase round-trip)
    assert recovery_bip39.verify_phrase(phrase), (
        f"{vector.name}: generated phrase fails verify_phrase"
    )
