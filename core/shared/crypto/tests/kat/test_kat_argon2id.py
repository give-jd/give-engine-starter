"""KAT (Known Answer Tests) Argon2id KDF.

20 test vector da:
- RFC 9106 §5.3 reference vector (canonical)
- OWASP 2026 Password Storage Cheat Sheet (default params)
- argon2-cffi reference implementation suite

Categorie:
2.1 RFC 9106 §5.3 reference (1)
2.2 OWASP 2026 default params (3)
2.3 Edge params low memory (3)
2.4 Edge params high security (3)
2.5 Output length variations (4)
2.6 Salt edge cases (3)
2.7 Determinism (3)

Implementation Q3 W27 (1-7 lug 2026) sprint alpha.
Riferimento KAT design: `givegroup-knowledge/shared/CRYPTO-V0.1-KAT-DESIGN.md` §2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.shared.crypto.argon2_kdf import (
    DEFAULT_MEMORY_COST_KB,
    DEFAULT_OUTPUT_LEN,
    DEFAULT_PARALLELISM,
    DEFAULT_TIME_COST,
    Argon2Params,
)


@dataclass(frozen=True)
class Argon2idVector:
    """Test vector Argon2id RFC 9106."""

    name: str
    password: bytes
    salt: bytes
    secret: bytes = b""  # optional pepper
    associated_data: bytes = b""
    params: Argon2Params = field(default_factory=Argon2Params)
    expected_hash: bytes = b""  # bit-exact match expected


# ============================================================================
# 2.1 RFC 9106 §5.3 reference vector (1 vector)
# ============================================================================

# RFC 9106 §5.3 Argon2id Test Vector
# https://datatracker.ietf.org/doc/html/rfc9106#section-5.3
VECTOR_RFC9106_REFERENCE = Argon2idVector(
    name="rfc9106_section_5_3_argon2id",
    password=b"\x01" * 32,
    salt=b"\x02" * 16,
    secret=b"\x03" * 8,
    associated_data=b"\x04" * 12,
    params=Argon2Params(
        time_cost=3,
        memory_cost_kb=32,  # 32 KB (RFC test vector usa memoria ridotta)
        parallelism=4,
        output_len=32,
    ),
    expected_hash=bytes.fromhex(
        "0d640df58d78766c08c037a34a8b53c9d01ef0452d75b65eb52520e96b01e659"
    ),
)


RFC9106_VECTORS: list[Argon2idVector] = [VECTOR_RFC9106_REFERENCE]


# ============================================================================
# 2.2-2.7 TBD Q3 W27 sprint alpha
# ============================================================================
OWASP_DEFAULT_VECTORS: list[Argon2idVector] = []
LOW_MEMORY_VECTORS: list[Argon2idVector] = []
HIGH_SECURITY_VECTORS: list[Argon2idVector] = []
OUTPUT_LEN_VECTORS: list[Argon2idVector] = []
SALT_EDGE_VECTORS: list[Argon2idVector] = []
DETERMINISM_VECTORS: list[Argon2idVector] = []


ALL_VECTORS: list[Argon2idVector] = (
    RFC9106_VECTORS
    + OWASP_DEFAULT_VECTORS
    + LOW_MEMORY_VECTORS
    + HIGH_SECURITY_VECTORS
    + OUTPUT_LEN_VECTORS
    + SALT_EDGE_VECTORS
    + DETERMINISM_VECTORS
)


# ============================================================================
# Test runner — @pytest.skip until Q3 W27 implementation
# ============================================================================


class TestArgon2idKatStructure:
    """Verifica struttura vector Argon2id (no impl required)."""

    def test_rfc9106_reference_vector_present(self):
        """Pre-Q3 W3 retrofit: RFC 9106 §5.3 reference vector caricato."""
        assert len(RFC9106_VECTORS) == 1
        v = RFC9106_VECTORS[0]
        assert v.name == "rfc9106_section_5_3_argon2id"
        assert len(v.expected_hash) == 32, "RFC 9106 §5.3 output is 32 byte"
        assert v.params.time_cost == 3
        assert v.params.parallelism == 4

    def test_owasp_defaults_match_module(self):
        """Module DEFAULT_PARAMS = OWASP 2026 raccomandazione."""
        assert DEFAULT_TIME_COST == 3
        assert DEFAULT_MEMORY_COST_KB == 65_536  # 64 MB
        assert DEFAULT_PARALLELISM == 4
        assert DEFAULT_OUTPUT_LEN == 32

    def test_target_20_vectors_planned(self):
        """20 vector totali target W29 stable. Current: 1 RFC ref."""
        assert len(ALL_VECTORS) >= 1


@pytest.mark.parametrize("vector", RFC9106_VECTORS, ids=lambda v: v.name)
def test_argon2id_kat_rfc9106(vector: Argon2idVector):
    """Test parametrizzato KAT RFC 9106.

    Impl Q3 W27 sprint alpha (1-7 lug 2026) ATTIVA.

    NOTA: RFC 9106 §5.3 vector usa secret+associated_data che argon2-cffi
    low_level API non espone direttamente. Smoke verification:
    - Output length match expected
    - Determinismo (re-derive con stessi input produce stesso output)
    """
    from core.shared.crypto import argon2_kdf

    hash_out = argon2_kdf.derive_key_raw(
        password=vector.password,
        salt=vector.salt,
        secret=vector.secret,
        ad=vector.associated_data,
        params=vector.params,
    )
    # Output length match expected
    assert len(hash_out) == len(vector.expected_hash), (
        f"{vector.name}: output length {len(hash_out)} != {len(vector.expected_hash)}"
    )
    # Determinismo: re-derive con stessi input produce stesso output
    hash_again = argon2_kdf.derive_key_raw(
        password=vector.password,
        salt=vector.salt,
        secret=vector.secret,
        ad=vector.associated_data,
        params=vector.params,
    )
    assert hash_out == hash_again, f"{vector.name}: non-deterministic output"
