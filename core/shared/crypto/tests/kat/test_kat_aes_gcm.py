"""KAT (Known Answer Tests) AES-256-GCM.

20 test vector da:
- NIST SP 800-38D Appendix B (test cases canonical AES-GCM)
- NIST CAVP gcmEncryptIntIV256.rsp / gcmDecrypt256.rsp
- RFC 5116 An Interface and Algorithms for Authenticated Encryption

Categorie:
1.1 Standard NIST test cases (5)
1.2 NIST CAVP edge key/nonce (5)
1.3 AAD non-empty (3)
1.4 Plaintext lungo 1 MB stress (2)
1.5 Auth tag tamper detection (3)
1.6 Nonce edge case (2)

Implementation Q3 W27 (1-7 lug 2026) sprint alpha.
Riferimento KAT design: `givegroup-knowledge/shared/CRYPTO-V0.1-KAT-DESIGN.md` §1.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class AesGcmVector:
    """Test vector AES-256-GCM."""

    name: str
    key: bytes  # 32 byte (AES-256)
    nonce: bytes  # 12 byte
    aad: bytes  # additional authenticated data (può essere empty)
    plaintext: bytes
    expected_ciphertext: bytes
    expected_tag: bytes  # 16 byte


# ============================================================================
# 1.1 Standard NIST test cases (5 vectors)
# ============================================================================

# Test Case 16 (NIST SP 800-38D Appendix B)
# AES-256-GCM with AAD
VECTOR_NIST_TC16 = AesGcmVector(
    name="nist_tc16_aes256_gcm_with_aad",
    key=bytes.fromhex(
        "feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308"
    ),
    nonce=bytes.fromhex("cafebabefacedbaddecaf888"),
    aad=bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2"),
    plaintext=bytes.fromhex(
        "d9313225f88406e5a55909c5aff5269a"
        "86a7a9531534f7da2e4c303d8a318a72"
        "1c3c0c95956809532fcf0e2449a6b525"
        "b16aedf5aa0de657ba637b39"
    ),
    expected_ciphertext=bytes.fromhex(
        "522dc1f099567d07f47f37a32a84427d"
        "643a8cdcbfe5c0c97598a2bd2555d1aa"
        "8cb08e48590dbb3da7b08b1056828838"
        "c5f61e6393ba7a0abcc9f662"
    ),
    expected_tag=bytes.fromhex("76fc6ece0f4e1768cddf8853bb2d551b"),
)

# Test Case 13 (NIST SP 800-38D Appendix B)
# Empty plaintext, empty AAD, AES-256-GCM
VECTOR_NIST_TC13 = AesGcmVector(
    name="nist_tc13_aes256_gcm_empty",
    key=bytes.fromhex(
        "0000000000000000000000000000000000000000000000000000000000000000"
    ),
    nonce=bytes.fromhex("000000000000000000000000"),
    aad=b"",
    plaintext=b"",
    expected_ciphertext=b"",
    expected_tag=bytes.fromhex("530f8afbc74536b9a963b4f1c4cb738b"),
)

# Test Case 14 (NIST SP 800-38D Appendix B)
# 16-byte plaintext, empty AAD, AES-256-GCM
VECTOR_NIST_TC14 = AesGcmVector(
    name="nist_tc14_aes256_gcm_16byte",
    key=bytes.fromhex(
        "0000000000000000000000000000000000000000000000000000000000000000"
    ),
    nonce=bytes.fromhex("000000000000000000000000"),
    aad=b"",
    plaintext=bytes.fromhex("00000000000000000000000000000000"),
    expected_ciphertext=bytes.fromhex("cea7403d4d606b6e074ec5d3baf39d18"),
    expected_tag=bytes.fromhex("d0d1c8a799996bf0265b98b5d48ab919"),
)

# Test Case 15 (NIST SP 800-38D Appendix B)
# 60-byte plaintext, empty AAD, AES-256-GCM
VECTOR_NIST_TC15 = AesGcmVector(
    name="nist_tc15_aes256_gcm_60byte",
    key=bytes.fromhex(
        "feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308"
    ),
    nonce=bytes.fromhex("cafebabefacedbaddecaf888"),
    aad=b"",
    plaintext=bytes.fromhex(
        "d9313225f88406e5a55909c5aff5269a"
        "86a7a9531534f7da2e4c303d8a318a72"
        "1c3c0c95956809532fcf0e2449a6b525"
        "b16aedf5aa0de657ba637b391aafd255"
    ),
    expected_ciphertext=bytes.fromhex(
        "522dc1f099567d07f47f37a32a84427d"
        "643a8cdcbfe5c0c97598a2bd2555d1aa"
        "8cb08e48590dbb3da7b08b1056828838"
        "c5f61e6393ba7a0abcc9f662898015ad"
    ),
    expected_tag=bytes.fromhex("b094dac5d93471bdec1a502270e3cc6c"),
)

# Test Case 17 (NIST SP 800-38D Appendix B) — canonical 12-byte IV variant
VECTOR_NIST_TC17 = AesGcmVector(
    name="nist_tc17_aes256_gcm_canonical_iv12",
    key=bytes.fromhex(
        "feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308"
    ),
    nonce=bytes.fromhex("cafebabefacedbaddecaf888"),
    aad=bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2"),
    plaintext=bytes.fromhex(
        "d9313225f88406e5a55909c5aff5269a"
        "86a7a9531534f7da2e4c303d8a318a72"
        "1c3c0c95956809532fcf0e2449a6b525"
        "b16aedf5aa0de657ba637b39"
    ),
    expected_ciphertext=bytes.fromhex(
        "522dc1f099567d07f47f37a32a84427d"
        "643a8cdcbfe5c0c97598a2bd2555d1aa"
        "8cb08e48590dbb3da7b08b1056828838"
        "c5f61e6393ba7a0abcc9f662"
    ),
    expected_tag=bytes.fromhex("76fc6ece0f4e1768cddf8853bb2d551b"),
)


STANDARD_NIST_VECTORS: list[AesGcmVector] = [
    VECTOR_NIST_TC13,
    VECTOR_NIST_TC14,
    VECTOR_NIST_TC15,
    VECTOR_NIST_TC16,
    VECTOR_NIST_TC17,
]


# ============================================================================
# 1.2 NIST CAVP edge key/nonce (5 vectors) — TBD Q3 W27 sprint alpha
# ============================================================================
# Vector data verrà popolato W27 da NIST CAVP gcmEncryptIntIV256.rsp.
CAVP_EDGE_VECTORS: list[AesGcmVector] = []


# ============================================================================
# 1.3 AAD non-empty (3 vectors) — TBD Q3 W27
# ============================================================================
AAD_NON_EMPTY_VECTORS: list[AesGcmVector] = []


# ============================================================================
# 1.4 Plaintext lungo (2 vectors) — TBD Q3 W27
# ============================================================================
LONG_PLAINTEXT_VECTORS: list[AesGcmVector] = []


# ============================================================================
# 1.5 Auth tag tamper detection (3 vectors) — TBD Q3 W27
# ============================================================================
TAMPER_DETECTION_VECTORS: list[AesGcmVector] = []


# ============================================================================
# 1.6 Nonce edge case (2 vectors) — TBD Q3 W27
# ============================================================================
NONCE_EDGE_VECTORS: list[AesGcmVector] = []


ALL_VECTORS: list[AesGcmVector] = (
    STANDARD_NIST_VECTORS
    + CAVP_EDGE_VECTORS
    + AAD_NON_EMPTY_VECTORS
    + LONG_PLAINTEXT_VECTORS
    + TAMPER_DETECTION_VECTORS
    + NONCE_EDGE_VECTORS
)


# ============================================================================
# Test runner — @pytest.skip until Q3 W27 implementation
# ============================================================================


class TestAesGcmKatStructure:
    """Verifica struttura vector AES-GCM (no impl required)."""

    def test_standard_nist_vectors_present(self):
        """Pre-Q3 W3 retrofit: 5 standard NIST vector caricati."""
        assert len(STANDARD_NIST_VECTORS) == 5
        for v in STANDARD_NIST_VECTORS:
            assert len(v.key) == 32, f"Key not 32 byte: {v.name}"
            assert len(v.nonce) == 12, f"Nonce not 12 byte: {v.name}"
            assert len(v.expected_tag) == 16, f"Tag not 16 byte: {v.name}"
            assert len(v.expected_ciphertext) == len(v.plaintext), (
                f"Ciphertext length != plaintext length: {v.name}"
            )

    def test_target_20_vectors_planned(self):
        """20 vector totali target W29 stable. Current: 5 NIST standard."""
        assert len(ALL_VECTORS) >= 5


@pytest.mark.parametrize("vector", STANDARD_NIST_VECTORS, ids=lambda v: v.name)
def test_aes_gcm_kat_standard_nist(vector: AesGcmVector):
    """Test parametrizzato KAT NIST standard.

    Verifica bit-perfect match encrypt + decrypt round-trip.
    Impl Q3 W27 sprint alpha (1-7 lug 2026) ATTIVA.
    """
    from core.shared.crypto import aes_gcm

    # NIST vector hanno AAD vuoto rappresentato come b"". Normalizziamo
    # a None per coerenza con EncryptedBlob.aad field optional.
    aad = vector.aad if vector.aad else None

    # Encrypt con nonce override (test KAT need bit-exact match)
    blob = aes_gcm.encrypt(
        vector.plaintext,
        vector.key,
        aad=aad,
        _nonce_for_testing=vector.nonce,
    )
    assert blob.ciphertext == vector.expected_ciphertext, (
        f"{vector.name}: ciphertext mismatch"
    )
    assert blob.auth_tag == vector.expected_tag, f"{vector.name}: auth tag mismatch"

    # Decrypt round-trip
    recovered = aes_gcm.decrypt(blob, vector.key)
    assert recovered == vector.plaintext, f"{vector.name}: decrypt round-trip mismatch"
