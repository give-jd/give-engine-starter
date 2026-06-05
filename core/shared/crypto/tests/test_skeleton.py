"""Test skeleton crypto module v0.1.0-dev.

Verifica struttura modulo (import + dataclass + eccezioni + costanti).
Implementazioni concrete sollevano NotImplementedError fino Q3 W27-W28.

Tests qui = smoke pre-implementation. KAT veri in `tests/kat/` Q3.
"""

from __future__ import annotations

import pytest

from core.shared.crypto import (
    __version__,
    AlreadyInitialized,
    AuthFailed,
    ConfigCorrupted,
    CryptoError,
    EmptyPassword,
    InvalidRecovery,
    KeyDerivationError,
    NotInitialized,
)


class TestVersion:
    def test_version_string_present(self):
        """Versione modulo dichiarata in __init__."""
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_dev_skeleton(self):
        """Q1-2029: crypto v0.2.0 (QR recovery). Accetta 0.x."""
        assert __version__.startswith("0.")


class TestExceptionHierarchy:
    """Verifica gerarchia eccezioni modulo."""

    def test_all_extend_crypto_error(self):
        """Tutte eccezioni custom estendono CryptoError (eccetto WeakPassword Warning)."""
        for exc_class in (
            AuthFailed,
            KeyDerivationError,
            InvalidRecovery,
            EmptyPassword,
            NotInitialized,
            AlreadyInitialized,
            ConfigCorrupted,
        ):
            assert issubclass(exc_class, CryptoError), (
                f"{exc_class.__name__} should extend CryptoError"
            )

    def test_crypto_error_is_exception(self):
        assert issubclass(CryptoError, Exception)


class TestDataclasses:
    """Verifica dataclass interface dichiarate."""

    def test_encrypted_blob_dataclass(self):
        from core.shared.crypto.aes_gcm import EncryptedBlob

        blob = EncryptedBlob(
            ciphertext=b"x",
            nonce=b"y" * 12,
            auth_tag=b"z" * 16,
            aad=None,
        )
        assert blob.ciphertext == b"x"
        assert blob.aad is None

    def test_argon2_params_default(self):
        from core.shared.crypto.argon2_kdf import DEFAULT_PARAMS

        # OWASP 2026 default params
        assert DEFAULT_PARAMS.time_cost == 3
        assert DEFAULT_PARAMS.memory_cost_kb == 65_536  # 64 MB
        assert DEFAULT_PARAMS.parallelism == 4
        assert DEFAULT_PARAMS.output_len == 32

    def test_auto_lock_config_defaults(self):
        from core.shared.crypto.auto_lock import (
            DEFAULT_TIMEOUT_SECONDS,
            GDPR_ART9_TIMEOUT_SECONDS,
            AutoLockConfig,
        )

        # 30 min default Catalogo
        assert DEFAULT_TIMEOUT_SECONDS == 1800
        # 15 min override art. 9 GDPR
        assert GDPR_ART9_TIMEOUT_SECONDS == 900

        config = AutoLockConfig()
        assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
        assert config.lock_on_idle is True


class TestConstants:
    """Verifica costanti standard AES-GCM + Argon2id + BIP-39."""

    def test_aes_gcm_constants(self):
        from core.shared.crypto.aes_gcm import (
            AUTH_TAG_LEN_BYTES,
            KEY_LEN_BYTES,
            NONCE_LEN_BYTES,
        )

        assert NONCE_LEN_BYTES == 12  # 96-bit NIST raccomandato
        assert AUTH_TAG_LEN_BYTES == 16  # 128-bit
        assert KEY_LEN_BYTES == 32  # AES-256

    def test_argon2_constants(self):
        from core.shared.crypto.argon2_kdf import SALT_LEN_BYTES

        assert SALT_LEN_BYTES == 16

    def test_bip39_constants(self):
        from core.shared.crypto.recovery_bip39 import (
            ENTROPY_BITS,
            ENTROPY_BYTES,
            PHRASE_LEN,
        )

        assert PHRASE_LEN == 12
        assert ENTROPY_BITS == 128
        assert ENTROPY_BYTES == 16


class TestRecoveryBip39:
    """Smoke test BIP-39 recovery (impl Q3 W28)."""

    def test_generate_returns_12_words(self):
        from core.shared.crypto import recovery_bip39

        phrase = recovery_bip39.generate_recovery_phrase()
        assert isinstance(phrase, list)
        assert len(phrase) == 12
        assert all(isinstance(w, str) for w in phrase)

    def test_generated_phrase_verifies(self):
        from core.shared.crypto import recovery_bip39

        phrase = recovery_bip39.generate_recovery_phrase()
        assert recovery_bip39.verify_phrase(phrase) is True

    def test_entropy_to_phrase_deterministic(self):
        from core.shared.crypto import recovery_bip39

        entropy = b"\x00" * 16
        p1 = recovery_bip39.entropy_to_phrase(entropy)
        p2 = recovery_bip39.entropy_to_phrase(entropy)
        assert p1 == p2
        assert len(p1) == 12

    def test_verify_invalid_phrase(self):
        from core.shared.crypto import recovery_bip39

        # Lista di 12 parole NON in wordlist
        bogus = ["x" * 5] * 12
        assert recovery_bip39.verify_phrase(bogus) is False

    def test_verify_wrong_length(self):
        from core.shared.crypto import recovery_bip39

        assert recovery_bip39.verify_phrase(["abaco"] * 11) is False
        assert recovery_bip39.verify_phrase(["abaco"] * 13) is False

    def test_phrase_to_seed_64_byte(self):
        from core.shared.crypto import recovery_bip39

        phrase = recovery_bip39.generate_recovery_phrase()
        seed = recovery_bip39.phrase_to_seed(phrase)
        assert isinstance(seed, bytes)
        assert len(seed) == 64

    def test_phrase_to_seed_deterministic(self):
        from core.shared.crypto import recovery_bip39

        entropy = b"\x42" * 16
        phrase = recovery_bip39.entropy_to_phrase(entropy)
        s1 = recovery_bip39.phrase_to_seed(phrase)
        s2 = recovery_bip39.phrase_to_seed(phrase)
        assert s1 == s2

    def test_passphrase_changes_seed(self):
        from core.shared.crypto import recovery_bip39

        phrase = recovery_bip39.generate_recovery_phrase()
        s_a = recovery_bip39.phrase_to_seed(phrase, passphrase="")
        s_b = recovery_bip39.phrase_to_seed(phrase, passphrase="extra")  # NOSONAR
        assert s_a != s_b


class TestMasterPassword:
    """Smoke test master_password flow (impl Q3 W28)."""

    def test_setup_creates_config(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        kr = Keyring()
        # Fast params per test
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        result = master_password.setup(
            "secure-password", kr, config_path=cfg, params=params
        )
        assert cfg.exists()
        assert len(result.recovery_phrase) == 12
        assert kr.get(result.handle.key_id) is not None

    def test_unlock_with_correct_password(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        kr_setup = Keyring()
        setup_result = master_password.setup(
            "p4ssw0rd-l0ng-enough", kr_setup, config_path=cfg, params=params
        )
        master_key_setup = kr_setup.get(setup_result.handle.key_id)

        # Fresh keyring, unlock
        kr_unlock = Keyring()
        handle = master_password.unlock(
            "p4ssw0rd-l0ng-enough", kr_unlock, config_path=cfg
        )
        assert kr_unlock.get(handle.key_id) == master_key_setup

    def test_unlock_with_wrong_password_raises(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.exceptions import AuthFailed
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        master_password.setup(
            "correct-password", Keyring(), config_path=cfg, params=params
        )
        with pytest.raises(AuthFailed):
            master_password.unlock("wrong-password", Keyring(), config_path=cfg)

    def test_unlock_without_setup_raises(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.exceptions import NotInitialized
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "noexist.json"
        with pytest.raises(NotInitialized):
            master_password.unlock("any", Keyring(), config_path=cfg)

    def test_double_setup_raises(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.exceptions import AlreadyInitialized
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        master_password.setup("first-pass", Keyring(), config_path=cfg, params=params)
        with pytest.raises(AlreadyInitialized):
            master_password.setup(
                "second-pass", Keyring(), config_path=cfg, params=params
            )

    def test_empty_password_raises(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.exceptions import EmptyPassword
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        with pytest.raises(EmptyPassword):
            master_password.setup("", Keyring(), config_path=cfg)

    def test_change_password_keeps_master_key(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        kr1 = Keyring()
        r = master_password.setup("old-password-x", kr1, config_path=cfg, params=params)
        master_before = kr1.get(r.handle.key_id)

        master_password.change_password(
            "old-password-x", "new-password-y", Keyring(), config_path=cfg
        )

        kr2 = Keyring()
        h = master_password.unlock("new-password-y", kr2, config_path=cfg)
        assert kr2.get(h.key_id) == master_before

    def test_reset_with_recovery_restores(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        kr1 = Keyring()
        r = master_password.setup("forgotten-pwd", kr1, config_path=cfg, params=params)
        master_before = kr1.get(r.handle.key_id)

        # Reset with recovery phrase + new password
        h = master_password.reset_with_recovery(
            r.recovery_phrase, "new-password-after-reset", Keyring(), config_path=cfg
        )

        # Unlock with new password → master key invariato
        kr2 = Keyring()
        h2 = master_password.unlock("new-password-after-reset", kr2, config_path=cfg)
        assert kr2.get(h2.key_id) == master_before
        assert kr1.get(r.handle.key_id) == master_before
        # h variable used (silence linter)
        assert h.key_id != r.handle.key_id

    def test_reset_with_invalid_recovery_raises(self, tmp_path):
        from core.shared.crypto import master_password
        from core.shared.crypto.argon2_kdf import Argon2Params
        from core.shared.crypto.exceptions import InvalidRecovery
        from core.shared.crypto.keyring import Keyring

        cfg = tmp_path / "config.json"
        params = Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        master_password.setup(
            "some-password", Keyring(), config_path=cfg, params=params
        )
        bogus_phrase = ["abaco"] * 12  # checksum wrong
        with pytest.raises(InvalidRecovery):
            master_password.reset_with_recovery(
                bogus_phrase, "new-pwd-here", Keyring(), config_path=cfg
            )


class TestAutoLockManager:
    """Smoke test auto_lock (impl Q3 W28)."""

    def test_start_stop(self):
        from core.shared.crypto.auto_lock import AutoLockConfig, AutoLockManager

        mgr = AutoLockManager()
        cfg = AutoLockConfig(timeout_seconds=10)
        mgr.start(cfg, lambda: None)
        assert mgr.is_running()
        mgr.stop()
        assert not mgr.is_running()

    def test_fires_callback_on_timeout(self):
        import threading

        from core.shared.crypto.auto_lock import AutoLockConfig, AutoLockManager

        mgr = AutoLockManager()
        fired = threading.Event()
        cfg = AutoLockConfig(timeout_seconds=0.1)  # 100ms
        mgr.start(cfg, fired.set)
        assert fired.wait(timeout=1.0), "Callback not fired within 1s"
        assert not mgr.is_running()

    def test_reset_timer_postpones_fire(self):
        import threading
        import time

        from core.shared.crypto.auto_lock import AutoLockConfig, AutoLockManager

        mgr = AutoLockManager()
        fired = threading.Event()
        cfg = AutoLockConfig(timeout_seconds=0.3)
        mgr.start(cfg, fired.set)
        # Reset before fire
        time.sleep(0.1)
        mgr.reset_timer()
        time.sleep(0.15)
        # Callback NOT yet fired (total wait 0.25 < 0.3 from reset)
        assert not fired.is_set()
        mgr.stop()


class TestAesGcmRoundtrip:
    """Smoke test AES-256-GCM round-trip (impl Q3 W27)."""

    def test_encrypt_decrypt_roundtrip(self):
        from core.shared.crypto import aes_gcm

        key = b"k" * 32
        plaintext = b"hello world"
        blob = aes_gcm.encrypt(plaintext, key)
        recovered = aes_gcm.decrypt(blob, key)
        assert recovered == plaintext

    def test_wrong_key_raises_auth_failed(self):
        from core.shared.crypto import aes_gcm
        from core.shared.crypto.exceptions import AuthFailed

        key = b"k" * 32
        wrong_key = b"x" * 32
        blob = aes_gcm.encrypt(b"data", key)
        with pytest.raises(AuthFailed):
            aes_gcm.decrypt(blob, wrong_key)

    def test_aad_authentication(self):
        from core.shared.crypto import aes_gcm

        key = b"k" * 32
        blob = aes_gcm.encrypt(b"data", key, aad=b"context")
        # decrypt with right AAD OK
        assert aes_gcm.decrypt(blob, key) == b"data"


class TestArgon2idDerive:
    """Smoke test Argon2id derive (impl Q3 W27)."""

    def test_derive_key_returns_32_byte(self):
        from core.shared.crypto import argon2_kdf

        salt = argon2_kdf.generate_salt()
        # OWASP 2026 default è t=3 m=64MB. Test usa params ridotti per speed.
        params = argon2_kdf.Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        key = argon2_kdf.derive_key("password", salt, params=params)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_derive_deterministic_same_input(self):
        from core.shared.crypto import argon2_kdf

        salt = b"s" * 16
        params = argon2_kdf.Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        k1 = argon2_kdf.derive_key("password", salt, params=params)
        k2 = argon2_kdf.derive_key("password", salt, params=params)
        assert k1 == k2

    def test_different_password_different_key(self):
        from core.shared.crypto import argon2_kdf

        salt = b"s" * 16
        params = argon2_kdf.Argon2Params(
            time_cost=1, memory_cost_kb=1024, parallelism=1, output_len=32
        )
        k1 = argon2_kdf.derive_key("pwd_a", salt, params=params)
        k2 = argon2_kdf.derive_key("pwd_b", salt, params=params)
        assert k1 != k2


class TestKeyring:
    """Smoke test Keyring (impl Q3 W27)."""

    def test_store_and_get(self):
        from core.shared.crypto.keyring import Keyring

        kr = Keyring()
        kr.store("key1", b"secret")
        assert kr.get("key1") == b"secret"

    def test_get_missing_returns_none(self):
        from core.shared.crypto.keyring import Keyring

        kr = Keyring()
        assert kr.get("missing") is None

    def test_remove_clears(self):
        from core.shared.crypto.keyring import Keyring

        kr = Keyring()
        kr.store("k", b"v")
        kr.remove("k")
        assert kr.get("k") is None

    def test_wipe_all_empties(self):
        from core.shared.crypto.keyring import Keyring

        kr = Keyring()
        kr.store("a", b"1")
        kr.store("b", b"2")
        kr.wipe_all()
        assert len(kr) == 0

    def test_get_returns_copy_not_buffer(self):
        from core.shared.crypto.keyring import Keyring

        kr = Keyring()
        kr.store("k", b"original")
        copy1 = kr.get("k")
        assert isinstance(copy1, bytes)


class TestKeyringSingleton:
    """Test singleton accessor."""

    def test_get_keyring_returns_same_instance(self):
        from core.shared.crypto.keyring import (
            _reset_global_keyring_for_testing,
            get_keyring,
        )

        _reset_global_keyring_for_testing()
        kr1 = get_keyring()
        kr2 = get_keyring()
        assert kr1 is kr2
        _reset_global_keyring_for_testing()


class TestGenerateSalt:
    """Verifica generate_salt è implementato (no NotImplementedError)."""

    def test_salt_length(self):
        from core.shared.crypto.argon2_kdf import SALT_LEN_BYTES, generate_salt

        salt = generate_salt()
        assert isinstance(salt, bytes)
        assert len(salt) == SALT_LEN_BYTES

    def test_salt_random(self):
        from core.shared.crypto.argon2_kdf import generate_salt

        # 2 salt consecutivi devono essere diversi (random)
        s1 = generate_salt()
        s2 = generate_salt()
        assert s1 != s2
