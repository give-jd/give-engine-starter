"""Master password flow: setup + unlock + change + reset_with_recovery.

Implementazione v0.1.0 Q3 W28 (8-14 lug 2026).

Flow:
1. setup(password) → genera salt + recovery + master_key + persist config
2. unlock(password) → re-derive KEK + decrypt master_key wrap + populate keyring
3. change_password(old, new) → re-derive KEK + re-encrypt master_key wrap
4. reset_with_recovery(phrase, new_pwd) → recovery seed → decrypt recovery_wrap → restore

Config file JSON schema (~/.givengine/crypto/config.json):
{
  "version": 1,
  "salt": <hex 16 byte>,
  "argon2_params": {time_cost, memory_cost_kb, parallelism, output_len},
  "kek_wrapped_master": <serialized EncryptedBlob>,
  "recovery_wrapped_master": <serialized EncryptedBlob>
}

NON contiene: master key plaintext (mai persistita).
"""

from __future__ import annotations

import json
import secrets
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.shared.crypto.aes_gcm import (
    KEY_LEN_BYTES,
    EncryptedBlob,
)
from core.shared.crypto.aes_gcm import decrypt as aes_decrypt
from core.shared.crypto.aes_gcm import encrypt as aes_encrypt
from core.shared.crypto.argon2_kdf import (
    DEFAULT_PARAMS,
    Argon2Params,
    derive_key,
    generate_salt,
)
from core.shared.crypto.exceptions import (
    AlreadyInitialized,
    AuthFailed,
    ConfigCorrupted,
    EmptyPassword,
    InvalidRecovery,
    NotInitialized,
    WeakPassword,
)
from core.shared.crypto.keyring import Keyring
from core.shared.crypto.recovery_bip39 import (
    generate_recovery_phrase,
    phrase_to_seed,
    verify_phrase,
)


# Min password length per warning WeakPassword
_MIN_PASSWORD_LEN: int = 12

# AAD per wrapping (tamper detection)
_AAD_KEK_WRAP: bytes = b"core/shared/crypto/master_password/kek_wrap/v1"
_AAD_RECOVERY_WRAP: bytes = b"core/shared/crypto/master_password/recovery_wrap/v1"

# Config schema version
_CONFIG_VERSION: int = 1
_ERR_KEYRING_REQUIRED = "keyring required"


def _default_config_path() -> Path:
    return Path.home() / ".givengine" / "crypto" / "config.json"


def _blob_to_dict(blob: EncryptedBlob) -> dict:
    return {
        "ciphertext": blob.ciphertext.hex(),
        "nonce": blob.nonce.hex(),
        "auth_tag": blob.auth_tag.hex(),
        "aad": blob.aad.hex() if blob.aad else None,
    }


def _blob_from_dict(d: dict) -> EncryptedBlob:
    return EncryptedBlob(
        ciphertext=bytes.fromhex(d["ciphertext"]),
        nonce=bytes.fromhex(d["nonce"]),
        auth_tag=bytes.fromhex(d["auth_tag"]),
        aad=bytes.fromhex(d["aad"]) if d.get("aad") else None,
    )


def _params_to_dict(p: Argon2Params) -> dict:
    return {
        "time_cost": p.time_cost,
        "memory_cost_kb": p.memory_cost_kb,
        "parallelism": p.parallelism,
        "output_len": p.output_len,
    }


def _params_from_dict(d: dict) -> Argon2Params:
    return Argon2Params(
        time_cost=d["time_cost"],
        memory_cost_kb=d["memory_cost_kb"],
        parallelism=d["parallelism"],
        output_len=d["output_len"],
    )


def _read_config(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigCorrupted(f"Cannot parse config {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != _CONFIG_VERSION:
        raise ConfigCorrupted(f"Invalid config version: {data.get('version')}")
    return data


def _write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _check_password_strength(password: str) -> None:
    if not password:
        raise EmptyPassword("Password cannot be empty")
    if len(password) < _MIN_PASSWORD_LEN:
        warnings.warn(
            f"Password length {len(password)} < {_MIN_PASSWORD_LEN} recommended",
            WeakPassword,
            stacklevel=3,
        )


@dataclass
class MasterKeyHandle:
    """Handle opaco di master key in keyring sessione."""

    key_id: str  # UUID4 reference in keyring
    derived_at: datetime
    argon2_params: Argon2Params


@dataclass
class SetupResult:
    """Risultato setup primo avvio."""

    handle: MasterKeyHandle
    recovery_phrase: list[str]  # 12 parole BIP39 italiane
    config_path: Path


def setup(
    password: str,
    keyring: Keyring,
    config_path: Path | None = None,
    params: Argon2Params = DEFAULT_PARAMS,
) -> SetupResult:
    """Setup primo avvio."""
    if keyring is None:
        raise TypeError(_ERR_KEYRING_REQUIRED)
    _check_password_strength(password)

    cfg_path = config_path or _default_config_path()
    if cfg_path.exists():
        raise AlreadyInitialized(f"Config already exists at {cfg_path}")

    # Generate master key + salt
    master_key = secrets.token_bytes(KEY_LEN_BYTES)
    salt = generate_salt()

    # Derive KEK from password
    kek = derive_key(password, salt, params=params)

    # Wrap master_key with KEK
    kek_wrap = aes_encrypt(master_key, kek, aad=_AAD_KEK_WRAP)

    # Recovery phrase + seed → first 32 byte = recovery_key
    recovery_phrase = generate_recovery_phrase()
    seed = phrase_to_seed(recovery_phrase)
    recovery_key = seed[:KEY_LEN_BYTES]

    # Wrap master_key with recovery_key
    recovery_wrap = aes_encrypt(master_key, recovery_key, aad=_AAD_RECOVERY_WRAP)

    # Persist config
    config = {
        "version": _CONFIG_VERSION,
        "salt": salt.hex(),
        "argon2_params": _params_to_dict(params),
        "kek_wrapped_master": _blob_to_dict(kek_wrap),
        "recovery_wrapped_master": _blob_to_dict(recovery_wrap),
    }
    _write_config(cfg_path, config)

    # Populate keyring + handle
    key_id = str(uuid.uuid4())
    keyring.store(key_id, master_key)
    handle = MasterKeyHandle(
        key_id=key_id,
        derived_at=datetime.now(timezone.utc),
        argon2_params=params,
    )
    return SetupResult(
        handle=handle, recovery_phrase=recovery_phrase, config_path=cfg_path
    )


def unlock(
    password: str,
    keyring: Keyring,
    config_path: Path | None = None,
) -> MasterKeyHandle:
    """Unlock sessione."""
    if keyring is None:
        raise TypeError(_ERR_KEYRING_REQUIRED)
    cfg_path = config_path or _default_config_path()
    if not cfg_path.exists():
        raise NotInitialized(f"No config at {cfg_path} — call setup() first")

    data = _read_config(cfg_path)
    try:
        salt = bytes.fromhex(data["salt"])
        params = _params_from_dict(data["argon2_params"])
        kek_wrap = _blob_from_dict(data["kek_wrapped_master"])
    except (KeyError, ValueError) as exc:
        raise ConfigCorrupted(f"Invalid config schema: {exc}") from exc

    kek = derive_key(password, salt, params=params)
    try:
        master_key = aes_decrypt(kek_wrap, kek)
    except AuthFailed as exc:
        raise AuthFailed("Wrong password (auth tag verification failed)") from exc

    key_id = str(uuid.uuid4())
    keyring.store(key_id, master_key)
    return MasterKeyHandle(
        key_id=key_id,
        derived_at=datetime.now(timezone.utc),
        argon2_params=params,
    )


def change_password(
    old: str,
    new: str,
    keyring: Keyring,
    config_path: Path | None = None,
) -> None:
    """Cambia password: unlock con vecchia, re-encrypt con nuova."""
    if keyring is None:
        raise TypeError(_ERR_KEYRING_REQUIRED)
    _check_password_strength(new)
    cfg_path = config_path or _default_config_path()
    if not cfg_path.exists():
        raise NotInitialized(f"No config at {cfg_path}")

    data = _read_config(cfg_path)
    try:
        salt = bytes.fromhex(data["salt"])
        params = _params_from_dict(data["argon2_params"])
        kek_wrap = _blob_from_dict(data["kek_wrapped_master"])
    except (KeyError, ValueError) as exc:
        raise ConfigCorrupted(f"Invalid config schema: {exc}") from exc

    # Verify old password by unwrap
    old_kek = derive_key(old, salt, params=params)
    try:
        master_key = aes_decrypt(kek_wrap, old_kek)
    except AuthFailed as exc:
        raise AuthFailed("Old password verification failed") from exc

    # Re-encrypt with new password (new salt = best practice)
    new_salt = generate_salt()
    new_kek = derive_key(new, new_salt, params=params)
    new_wrap = aes_encrypt(master_key, new_kek, aad=_AAD_KEK_WRAP)

    data["salt"] = new_salt.hex()
    data["kek_wrapped_master"] = _blob_to_dict(new_wrap)
    _write_config(cfg_path, data)


def reset_with_recovery(
    recovery_phrase: list[str],
    new_password: str,
    keyring: Keyring,
    config_path: Path | None = None,
) -> MasterKeyHandle:
    """Reset password con frase di recupero BIP-39."""
    if keyring is None:
        raise TypeError(_ERR_KEYRING_REQUIRED)
    if not verify_phrase(recovery_phrase):
        raise InvalidRecovery("Recovery phrase checksum/wordlist verification failed")
    _check_password_strength(new_password)

    cfg_path = config_path or _default_config_path()
    if not cfg_path.exists():
        raise NotInitialized(f"No config at {cfg_path}")

    data = _read_config(cfg_path)
    try:
        params = _params_from_dict(data["argon2_params"])
        recovery_wrap = _blob_from_dict(data["recovery_wrapped_master"])
    except (KeyError, ValueError) as exc:
        raise ConfigCorrupted(f"Invalid config schema: {exc}") from exc

    seed = phrase_to_seed(recovery_phrase)
    recovery_key = seed[:KEY_LEN_BYTES]
    try:
        master_key = aes_decrypt(recovery_wrap, recovery_key)
    except AuthFailed as exc:
        raise InvalidRecovery(
            "Recovery phrase does not match config (wrong phrase or corrupt config)"
        ) from exc

    # Re-wrap with new password
    new_salt = generate_salt()
    new_kek = derive_key(new_password, new_salt, params=params)
    new_wrap = aes_encrypt(master_key, new_kek, aad=_AAD_KEK_WRAP)
    data["salt"] = new_salt.hex()
    data["kek_wrapped_master"] = _blob_to_dict(new_wrap)
    _write_config(cfg_path, data)

    key_id = str(uuid.uuid4())
    keyring.store(key_id, master_key)
    return MasterKeyHandle(
        key_id=key_id,
        derived_at=datetime.now(timezone.utc),
        argon2_params=params,
    )
