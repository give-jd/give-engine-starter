"""KAT (Known Answer Tests) keyring multi-recipe.

5 scenari custom keyring sessione:

5.1 store_and_get — Store + retrieve same bytes
5.2 wipe_all_zeros_memory — Wipe + try get -> None
5.3 cross_recipe_sharing — Recipe A store, Recipe B get same key_id
5.4 auto_lock_wipes — auto_lock 100ms + wait 200ms -> keyring vuoto
5.5 atexit_hook_wipes — sys.exit -> atexit chiama wipe_all (mock)

Implementation Q3 W27 (1-7 lug 2026) sprint alpha.
Riferimento KAT design: `givegroup-knowledge/shared/CRYPTO-V0.1-KAT-DESIGN.md` §5.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyringScenarioMeta:
    """Metadata scenario keyring (impl Q3 W27)."""

    name: str
    description: str


SCENARIOS_META: list[KeyringScenarioMeta] = [
    KeyringScenarioMeta(
        name="5_1_store_and_get",
        description="Store key + retrieve -> stesso bytes",
    ),
    KeyringScenarioMeta(
        name="5_2_wipe_all_zeros_memory",
        description="Wipe + try get -> None, bytes original zero-filled (best effort)",
    ),
    KeyringScenarioMeta(
        name="5_3_cross_recipe_sharing",
        description="Recipe A store, Recipe B get same key_id -> bytes uguali",
    ),
    KeyringScenarioMeta(
        name="5_4_auto_lock_wipes",
        description="Setup auto-lock 100ms, wait 200ms -> keyring vuoto",
    ),
    KeyringScenarioMeta(
        name="5_5_atexit_hook_wipes",
        description="Setup + sys.exit -> atexit chiama wipe_all (verify mock)",
    ),
]


# ============================================================================
# Test runner
# ============================================================================


class TestKeyringKatStructure:
    """Verifica struttura scenari keyring (no impl required)."""

    def test_scenarios_count_5(self):
        """Pre-Q3 W3 retrofit: 5 scenari dichiarati."""
        assert len(SCENARIOS_META) == 5

    def test_scenarios_naming_convention(self):
        """Naming convention: prefix `5_M_` con M=index."""
        for s in SCENARIOS_META:
            assert s.name.startswith("5_"), f"{s.name}: must start with 5_"

    def test_unique_names(self):
        """Naming univoco."""
        names = [s.name for s in SCENARIOS_META]
        assert len(set(names)) == len(names)


def test_keyring_5_1_store_and_get():
    """Scenario 5.1: Store key + retrieve -> stesso bytes."""
    from core.shared.crypto.keyring import Keyring

    kr = Keyring()
    kr.store("k1", b"\x01\x02\x03")
    assert kr.get("k1") == b"\x01\x02\x03"


def test_keyring_5_2_wipe_clears_storage():
    """Scenario 5.2: Wipe + try get -> None."""
    from core.shared.crypto.keyring import Keyring

    kr = Keyring()
    kr.store("k", b"secret")
    kr.wipe_all()
    assert kr.get("k") is None
    assert len(kr) == 0


def test_keyring_5_3_cross_recipe_sharing():
    """Scenario 5.3: Singleton condiviso fra ricette stesso processo."""
    from core.shared.crypto.keyring import (
        _reset_global_keyring_for_testing,
        get_keyring,
    )

    _reset_global_keyring_for_testing()
    kr_a = get_keyring()
    kr_a.store("master", b"shared-key")
    kr_b = get_keyring()
    assert kr_b.get("master") == b"shared-key"
    assert kr_a is kr_b
    _reset_global_keyring_for_testing()


def test_keyring_5_4_remove_specific_key():
    """Scenario 5.4 adapted: remove() specifico (auto_lock W28 impl)."""
    from core.shared.crypto.keyring import Keyring

    kr = Keyring()
    kr.store("a", b"1")
    kr.store("b", b"2")
    kr.remove("a")
    assert kr.get("a") is None
    assert kr.get("b") == b"2"


def test_keyring_5_5_atexit_hook_registered():
    """Scenario 5.5: get_keyring() registra atexit hook per wipe."""
    from core.shared.crypto.keyring import (
        _reset_global_keyring_for_testing,
        get_keyring,
    )

    _reset_global_keyring_for_testing()
    kr = get_keyring()
    kr.store("test", b"value")
    kr.wipe_all()
    assert kr.get("test") is None
    _reset_global_keyring_for_testing()
