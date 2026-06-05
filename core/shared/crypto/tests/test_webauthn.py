"""Tests WebAuthn / FIDO2 v0.3.0."""

from __future__ import annotations

import base64
import json

import pytest

from core.shared.crypto import webauthn
from core.shared.crypto.webauthn import (
    CHALLENGE_LEN,
    WRAP_KEY_LEN,
    RegisteredToken,
    TokenAssertionFailed,
    TokenNotRegistered,
    WebAuthnError,
    WebAuthnState,
)


CRED_ID_1 = "abc123def456789012345678"
COSE_KEY_1 = "a40102032620012158208de4a89dabfb2c0fc04b3d99a5cd5b18b16f9c2e7a3a4c5dab9b80fdf3fc41a4225820"


def _cd(challenge: bytes) -> bytes:
    """clientDataJSON sintetico con la challenge attesa (base64url, spec WebAuthn)."""
    b64 = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()
    return json.dumps({"type": "webauthn.get", "challenge": b64}).encode()


class TestGeneraChallenge:
    def test_lunghezza(self):
        c = webauthn.genera_challenge()
        assert len(c) == CHALLENGE_LEN

    def test_random(self):
        a, b = webauthn.genera_challenge(), webauthn.genera_challenge()
        assert a != b


class TestUserHandle:
    def test_deterministico(self):
        salt = b"\x01" * 16
        h1 = webauthn.genera_user_handle(salt)
        h2 = webauthn.genera_user_handle(salt)
        assert h1 == h2
        assert len(h1) == 16

    def test_salt_diverso_handle_diverso(self):
        h1 = webauthn.genera_user_handle(b"\x01" * 16)
        h2 = webauthn.genera_user_handle(b"\x02" * 16)
        assert h1 != h2


class TestRegistraToken:
    def test_ok(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1, label="YubiKey-5")
        assert len(s.tokens) == 1
        assert s.tokens[0].label == "YubiKey-5"

    def test_credential_id_obbligatorio(self):
        s = WebAuthnState()
        with pytest.raises(WebAuthnError, match="credential_id"):
            webauthn.registra_token(s, "", COSE_KEY_1)

    def test_public_key_obbligatorio(self):
        s = WebAuthnState()
        with pytest.raises(WebAuthnError, match="public_key_cose"):
            webauthn.registra_token(s, CRED_ID_1, "")

    def test_duplicato_rifiutato(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        with pytest.raises(WebAuthnError, match="gia"):
            webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)

    def test_multipli_token_ok(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1, label="primary")
        webauthn.registra_token(s, "xyz789", COSE_KEY_1, label="backup")
        assert len(s.tokens) == 2


class TestRimuoviToken:
    def test_ok(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        webauthn.rimuovi_token(s, CRED_ID_1)
        assert s.tokens == []

    def test_non_esiste(self):
        s = WebAuthnState()
        with pytest.raises(TokenNotRegistered):
            webauthn.rimuovi_token(s, "non-esiste")


class TestWrapKey:
    def test_crea_wrap_key(self):
        k = webauthn.crea_wrap_key()
        assert len(k) == WRAP_KEY_LEN

    def test_wrap_key_random(self):
        a, b = webauthn.crea_wrap_key(), webauthn.crea_wrap_key()
        assert a != b

    def test_cifra_decifra_roundtrip(self):
        wrap = webauthn.crea_wrap_key()
        master = b"\x00" * 32
        blob = webauthn.cifra_wrap_key_con_master(wrap, master)
        recovered = webauthn.decifra_wrap_key_con_master(blob, master)
        assert recovered == wrap

    def test_master_key_lunghezza_invalida(self):
        wrap = webauthn.crea_wrap_key()
        with pytest.raises(WebAuthnError, match="32 byte"):
            webauthn.cifra_wrap_key_con_master(wrap, b"\x00" * 16)

    def test_master_errata_solleva(self):
        wrap = webauthn.crea_wrap_key()
        blob = webauthn.cifra_wrap_key_con_master(wrap, b"\x00" * 32)
        with pytest.raises(TokenAssertionFailed):
            webauthn.decifra_wrap_key_con_master(blob, b"\xff" * 32)


class TestStateSerializzazione:
    def test_to_from_json(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1, label="YubiKey-5")
        s.wrap_key_blob_hex = "deadbeef" * 8
        js = s.to_json()
        s2 = WebAuthnState.from_json(js)
        assert s2.rp_id == s.rp_id
        assert len(s2.tokens) == 1
        assert s2.tokens[0].credential_id == CRED_ID_1
        assert s2.wrap_key_blob_hex == s.wrap_key_blob_hex

    def test_state_vuoto_round_trip(self):
        s = WebAuthnState()
        s2 = WebAuthnState.from_json(s.to_json())
        assert s2.tokens == []


class TestVerificaAssertionMock:
    def test_credential_non_registrato(self):
        s = WebAuthnState()
        with pytest.raises(TokenNotRegistered):
            webauthn.verifica_assertion(
                s,
                "x" * 16,
                b"chall",
                b"sig",
                b"\x00" * 37,
                b"{}",
                verify_signature=lambda *a: True,
            )

    def test_verify_signature_ok(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        auth_data = b"\x00" * 33 + (5).to_bytes(4, "big")
        result = webauthn.verifica_assertion(
            s,
            CRED_ID_1,
            b"chall",
            b"sig",
            auth_data,
            _cd(b"chall"),
            verify_signature=lambda pk, sig, ad, cd: True,
        )
        assert result is True
        assert s.tokens[0].sign_count == 5

    def test_verify_signature_failed(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        auth_data = b"\x00" * 33 + (5).to_bytes(4, "big")
        with pytest.raises(TokenAssertionFailed, match="Custom verifier"):
            webauthn.verifica_assertion(
                s,
                CRED_ID_1,
                b"chall",
                b"sig",
                auth_data,
                _cd(b"chall"),
                verify_signature=lambda *a: False,
            )

    def test_sign_count_regressione_clone(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        s.tokens[0].sign_count = 10
        auth_data = b"\x00" * 33 + (5).to_bytes(4, "big")
        with pytest.raises(TokenAssertionFailed, match="regressione"):
            webauthn.verifica_assertion(
                s,
                CRED_ID_1,
                b"chall",
                b"sig",
                auth_data,
                _cd(b"chall"),
                verify_signature=lambda *a: True,
            )

    def test_sign_count_progressione_ok(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        s.tokens[0].sign_count = 5
        auth_data = b"\x00" * 33 + (6).to_bytes(4, "big")
        result = webauthn.verifica_assertion(
            s,
            CRED_ID_1,
            b"chall",
            b"sig",
            auth_data,
            _cd(b"chall"),
            verify_signature=lambda *a: True,
        )
        assert result is True
        assert s.tokens[0].sign_count == 6

    def test_challenge_mismatch_replay(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        auth_data = b"\x00" * 33 + (5).to_bytes(4, "big")
        with pytest.raises(TokenAssertionFailed, match="challenge mismatch"):
            webauthn.verifica_assertion(
                s,
                CRED_ID_1,
                b"expected-challenge",
                b"sig",
                auth_data,
                _cd(b"other-challenge"),
                verify_signature=lambda *a: True,
            )

    def test_challenge_assente(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        auth_data = b"\x00" * 33 + (5).to_bytes(4, "big")
        with pytest.raises(TokenAssertionFailed, match="'challenge'"):
            webauthn.verifica_assertion(
                s,
                CRED_ID_1,
                b"chall",
                b"sig",
                auth_data,
                b"{}",
                verify_signature=lambda *a: True,
            )


class TestListTokens:
    def test_vuoto(self):
        assert webauthn.list_tokens(WebAuthnState()) == []

    def test_con_tokens(self):
        s = WebAuthnState()
        webauthn.registra_token(
            s, CRED_ID_1, COSE_KEY_1, label="primary", aaguid="aaguid-yubikey-5"
        )
        webauthn.registra_token(s, "xyz789abc", COSE_KEY_1, label="backup")
        out = webauthn.list_tokens(s)
        assert len(out) == 2
        assert out[0]["label"] == "primary"
        assert out[0]["aaguid"] == "aaguid-yubikey-5"
        assert "credential_id_prefix" in out[0]
        assert len(out[0]["credential_id_prefix"]) == 8


class TestHaTokenRegistrato:
    def test_no_token(self):
        assert webauthn.ha_token_registrato(WebAuthnState()) is False

    def test_con_token(self):
        s = WebAuthnState()
        webauthn.registra_token(s, CRED_ID_1, COSE_KEY_1)
        assert webauthn.ha_token_registrato(s) is True


class TestRegisteredTokenDataclass:
    def test_from_dict(self):
        d = {
            "credential_id": CRED_ID_1,
            "public_key_cose": COSE_KEY_1,
            "sign_count": 0,
            "label": "test",
            "registered_at": "2026-05-30T00:00:00+00:00",
            "aaguid": None,
        }
        t = RegisteredToken.from_dict(d)
        assert t.credential_id == CRED_ID_1
        assert t.sign_count == 0

    def test_to_dict(self):
        t = RegisteredToken(
            credential_id=CRED_ID_1,
            public_key_cose=COSE_KEY_1,
            sign_count=3,
            label="X",
            registered_at="2026-05-30T00:00:00+00:00",
        )
        d = t.to_dict()
        assert d["credential_id"] == CRED_ID_1
        assert d["sign_count"] == 3
