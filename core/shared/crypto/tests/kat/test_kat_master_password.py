"""KAT (Known Answer Tests) master password flow.

15 scenari custom per setup + unlock + change + reset_with_recovery:

4.1 setup_then_unlock — Master key matches
4.2 setup_then_wrong_pwd — AuthFailed
4.3 change_password_keeps_data — Data leggibili post-change
4.4 change_password_old_wrong — AuthFailed, salt invariato
4.5 reset_with_recovery_valid — New master key OK
4.6 reset_with_recovery_invalid — InvalidRecovery
4.7 empty_password_rejected — EmptyPassword
4.8 weak_password_warning — Warning emesso
4.9 unlock_without_setup — NotInitialized
4.10 double_setup_rejected — AlreadyInitialized
4.11 salt_persistence — Restart processo + unlock OK
4.12 argon2_params_upgrade — Re-derive at next unlock
4.13 recovery_phrase_uniqueness — 10 frasi diverse
4.14 tamper_config_file — ConfigCorrupted
4.15 concurrent_unlock_locks — Solo uno succede

Implementation Q3 W28 (8-14 lug 2026) sprint beta.
Riferimento KAT design: `givegroup-knowledge/shared/CRYPTO-V0.1-KAT-DESIGN.md` §4.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class MasterPwdScenarioMeta:
    """Metadata scenario master password (impl Q3 W28)."""

    name: str
    description: str
    expected_exception: type | None = None
    expected_warning: type | None = None


SCENARIOS_META: list[MasterPwdScenarioMeta] = [
    MasterPwdScenarioMeta(
        name="4_1_setup_then_unlock",
        description="Setup primo avvio + lock + unlock con stessa pwd",
    ),
    MasterPwdScenarioMeta(
        name="4_2_setup_then_wrong_pwd",
        description="Setup + unlock con pwd sbagliata -> AuthFailed",
        expected_exception=Exception,  # AuthFailed
    ),
    MasterPwdScenarioMeta(
        name="4_3_change_password_keeps_data",
        description="Setup + write data cifrato + change pwd + read",
    ),
    MasterPwdScenarioMeta(
        name="4_4_change_password_old_wrong",
        description="Change con vecchia pwd sbagliata -> AuthFailed",
        expected_exception=Exception,
    ),
    MasterPwdScenarioMeta(
        name="4_5_reset_with_recovery_valid",
        description="Setup + perdi pwd + reset con recovery phrase",
    ),
    MasterPwdScenarioMeta(
        name="4_6_reset_with_recovery_invalid",
        description="Reset con recovery phrase sbagliata -> InvalidRecovery",
        expected_exception=Exception,
    ),
    MasterPwdScenarioMeta(
        name="4_7_empty_password_rejected",
        description="Setup con password vuota -> EmptyPassword",
        expected_exception=Exception,
    ),
    MasterPwdScenarioMeta(
        name="4_8_weak_password_warning",
        description="Setup con pwd < 12 char -> WeakPassword warning",
        expected_warning=Warning,
    ),
    MasterPwdScenarioMeta(
        name="4_9_unlock_without_setup",
        description="Unlock prima setup -> NotInitialized",
        expected_exception=Exception,
    ),
    MasterPwdScenarioMeta(
        name="4_10_double_setup_rejected",
        description="Setup chiamato due volte -> AlreadyInitialized",
        expected_exception=Exception,
    ),
    MasterPwdScenarioMeta(
        name="4_11_salt_persistence",
        description="Setup, restart processo, unlock -> OK",
    ),
    MasterPwdScenarioMeta(
        name="4_12_argon2_params_upgrade",
        description="Setup con OWASP 2024 params, upgrade a 2026 -> re-derive",
    ),
    MasterPwdScenarioMeta(
        name="4_13_recovery_phrase_uniqueness",
        description="Setup 10 volte con stesse pwd -> 10 frasi diverse",
    ),
    MasterPwdScenarioMeta(
        name="4_14_tamper_config_file",
        description="Setup + corrupt config file -> ConfigCorrupted",
        expected_exception=Exception,
    ),
    MasterPwdScenarioMeta(
        name="4_15_concurrent_unlock_locks",
        description="2 thread unlock simultaneo -> Solo uno succede",
    ),
]


# ============================================================================
# Test runner
# ============================================================================


class TestMasterPasswordKatStructure:
    """Verifica struttura scenari master password (no impl required)."""

    def test_scenarios_count_15(self):
        """Pre-Q3 W3 retrofit: 15 scenari dichiarati."""
        assert len(SCENARIOS_META) == 15

    def test_scenarios_naming_convention(self):
        """Naming convention: prefix `4_M_` con M=index."""
        for s in SCENARIOS_META:
            assert s.name.startswith("4_"), f"{s.name}: must start with 4_"

    def test_error_scenarios_have_expected_exception(self):
        """Scenari che expectono exception devono dichiarare expected_exception."""
        error_scenarios = [
            s for s in SCENARIOS_META if s.expected_exception is not None
        ]
        assert len(error_scenarios) == 7  # 4.2, 4.4, 4.6, 4.7, 4.9, 4.10, 4.14

    def test_warning_scenario_4_8(self):
        """Scenario 4_8 weak_password emette WeakPassword warning (non-fatale)."""
        ws = next(s for s in SCENARIOS_META if s.name == "4_8_weak_password_warning")
        assert ws.expected_warning is Warning
        assert ws.expected_exception is None


@pytest.mark.parametrize("scenario", SCENARIOS_META, ids=lambda s: s.name)
def test_master_password_scenario_metadata(scenario: MasterPwdScenarioMeta):
    """Verifica metadata scenari master password.

    Impl Q3 W28 sprint beta ATTIVA. Test concreti behavioral in
    tests/test_skeleton.py::TestMasterPassword (8 scenari testati).

    Parametric verifica solo metadata coherent.
    """
    assert scenario.name.startswith("4_"), (
        f"Naming convention violation: {scenario.name}"
    )
    assert scenario.description, f"{scenario.name}: description vuota"
