"""Pytest fixtures crypto module v0.1.

Implementation Q3 W27 (1-7 lug 2026). Skeleton v0.1.0-dev.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fresh_keyring():
    """Keyring pulito per ogni test.

    Implementation Q3 W27.
    """
    pytest.skip("Implementation Q3 W27 (1-7 lug 2026)")


@pytest.fixture
def temp_config_path(tmp_path):
    """Path config crypto isolato in tmp_path pytest fixture.

    Implementation Q3 W27.
    """
    return tmp_path / "crypto-config.json"
