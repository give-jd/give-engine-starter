"""WebAuthn / FIDO2 hardware token integration v0.3.0.

Supporto FIDO2 (CTAP2) per master password unlock alternativo:
- Registrazione token U2F/FIDO2 (YubiKey, Solokey, Google Titan, Feitian)
- Verifica assertion via challenge-response
- Multipli token registrabili per recovery

Architettura:
- Token NON deriva master key direttamente (sarebbe insicuro se token perso)
- Token sblocca uno "wrap key" cifrato che cifra il master key Argon2
- Pattern simile a Bitwarden / 1Password hardware unlock

Dipendenza opzionale: `fido2` (Yubico python-fido2 library).
Fallback: master password puro se token non disponibile.

Specifiche:
- RP ID: "give-engine.local" (localhost)
- User handle: hash(master_password_salt) -> stable identifier
- Authenticator: cross-platform (USB/NFC/BLE)
- Algorithm: ES256 (-7) primary, RS256 (-257) fallback
"""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


RP_ID = "give-engine.local"
RP_NAME = "Gi.Ve Engine Local"
CHALLENGE_LEN = 32
WRAP_KEY_LEN = 32


class WebAuthnError(Exception):
    pass


class TokenNotRegistered(WebAuthnError):
    pass


class TokenAssertionFailed(WebAuthnError):
    pass


@dataclass
class RegisteredToken:
    credential_id: str
    public_key_cose: str
    sign_count: int
    label: str
    registered_at: str
    aaguid: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> RegisteredToken:
        return cls(**d)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WebAuthnState:
    rp_id: str = RP_ID
    rp_name: str = RP_NAME
    tokens: list[RegisteredToken] = field(default_factory=list)
    wrap_key_blob_hex: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "rp_id": self.rp_id,
                "rp_name": self.rp_name,
                "tokens": [t.to_dict() for t in self.tokens],
                "wrap_key_blob_hex": self.wrap_key_blob_hex,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, s: str) -> WebAuthnState:
        d = json.loads(s)
        return cls(
            rp_id=d.get("rp_id", RP_ID),
            rp_name=d.get("rp_name", RP_NAME),
            tokens=[RegisteredToken.from_dict(t) for t in d.get("tokens", [])],
            wrap_key_blob_hex=d.get("wrap_key_blob_hex"),
        )


def genera_challenge() -> bytes:
    return secrets.token_bytes(CHALLENGE_LEN)


def genera_user_handle(master_password_salt: bytes) -> bytes:
    import hashlib

    return hashlib.sha256(b"give-engine:" + master_password_salt).digest()[:16]


def registra_token(
    state: WebAuthnState,
    credential_id: str,
    public_key_cose: str,
    label: str = "YubiKey",
    aaguid: str | None = None,
) -> WebAuthnState:
    if not credential_id:
        raise WebAuthnError("credential_id obbligatorio")
    if not public_key_cose:
        raise WebAuthnError("public_key_cose obbligatorio")
    for t in state.tokens:
        if t.credential_id == credential_id:
            raise WebAuthnError(f"token {credential_id[:8]}... gia' registrato")
    token = RegisteredToken(
        credential_id=credential_id,
        public_key_cose=public_key_cose,
        sign_count=0,
        label=label,
        registered_at=datetime.now(timezone.utc).isoformat(),
        aaguid=aaguid,
    )
    state.tokens.append(token)
    return state


def rimuovi_token(state: WebAuthnState, credential_id: str) -> WebAuthnState:
    before = len(state.tokens)
    state.tokens = [t for t in state.tokens if t.credential_id != credential_id]
    if len(state.tokens) == before:
        raise TokenNotRegistered(f"credential_id {credential_id[:8]}... non trovato")
    return state


def crea_wrap_key() -> bytes:
    return secrets.token_bytes(WRAP_KEY_LEN)


def cifra_wrap_key_con_master(wrap_key: bytes, master_key: bytes) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise WebAuthnError("cryptography mancante. pip install cryptography") from e
    if len(master_key) != 32:
        raise WebAuthnError(
            f"master_key deve essere 32 byte, trovati {len(master_key)}"
        )
    nonce = secrets.token_bytes(12)
    ct = AESGCM(master_key).encrypt(nonce, wrap_key, None)
    return (nonce + ct).hex()


def decifra_wrap_key_con_master(blob_hex: str, master_key: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise WebAuthnError("cryptography mancante") from e
    blob = bytes.fromhex(blob_hex)
    nonce, ct = blob[:12], blob[12:]
    try:
        return AESGCM(master_key).decrypt(nonce, ct, None)
    except Exception as e:
        raise TokenAssertionFailed(
            "Decifratura wrap_key fallita (master password errata)"
        ) from e


def _verify_challenge(client_data_json: bytes, expected: bytes) -> None:
    """Anti-replay: la challenge in clientDataJSON deve combaciare con quella attesa.

    Step WebAuthn obbligatorio (verify C.challenge == options.challenge). La
    challenge è codificata base64url senza padding nello standard.

    Raises:
        TokenAssertionFailed: clientDataJSON malformato, challenge assente o diversa.
    """
    try:
        cd = json.loads(client_data_json)
    except ValueError as e:
        raise TokenAssertionFailed(f"clientDataJSON non valido: {e}") from e
    raw = cd.get("challenge") if isinstance(cd, dict) else None
    if not isinstance(raw, str):
        raise TokenAssertionFailed("clientDataJSON privo del campo 'challenge'")
    pad = "=" * (-len(raw) % 4)
    try:
        got = base64.urlsafe_b64decode(raw + pad)
    except ValueError as e:
        raise TokenAssertionFailed(
            f"challenge clientData non decodificabile: {e}"
        ) from e
    if not secrets.compare_digest(got, expected):
        raise TokenAssertionFailed("challenge mismatch (possibile replay)")


def verifica_assertion(
    state: WebAuthnState,
    credential_id: str,
    challenge: bytes,
    signature: bytes,
    authenticator_data: bytes,
    client_data_json: bytes,
    verify_signature: Any = None,
) -> bool:
    token = next((t for t in state.tokens if t.credential_id == credential_id), None)
    if token is None:
        raise TokenNotRegistered(f"credential_id {credential_id[:8]}... non trovato")
    _verify_challenge(client_data_json, challenge)
    if verify_signature is None:
        try:
            from fido2.cose import CoseKey

            cose_key = CoseKey.parse(bytes.fromhex(token.public_key_cose))
            signed_data = authenticator_data + _sha256(client_data_json)
            cose_key.verify(signed_data, signature)
        except ImportError as e:
            raise WebAuthnError("fido2 library mancante. pip install fido2") from e
        except Exception as e:
            raise TokenAssertionFailed(f"Verifica firma fallita: {e}") from e
    else:
        if not verify_signature(
            token.public_key_cose, signature, authenticator_data, client_data_json
        ):
            raise TokenAssertionFailed("Custom verifier rigettato")
    counter = int.from_bytes(authenticator_data[33:37], "big")
    if counter <= token.sign_count and token.sign_count != 0:
        raise TokenAssertionFailed(
            f"sign_count regressione (clonazione token sospetta): "
            f"prev={token.sign_count}, new={counter}"
        )
    token.sign_count = counter
    return True


def _sha256(data: bytes) -> bytes:
    import hashlib

    return hashlib.sha256(data).digest()


def list_tokens(state: WebAuthnState) -> list[dict]:
    return [
        {
            "credential_id_prefix": t.credential_id[:8],
            "label": t.label,
            "registered_at": t.registered_at,
            "sign_count": t.sign_count,
            "aaguid": t.aaguid,
        }
        for t in state.tokens
    ]


def ha_token_registrato(state: WebAuthnState) -> bool:
    return len(state.tokens) > 0
