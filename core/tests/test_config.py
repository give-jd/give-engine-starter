"""Test per core/config.py (env loading + mode detection Lemon Squeezy)."""

from __future__ import annotations

import httpx
import pytest

from core import config


@pytest.fixture(autouse=True)
def _clean_cache():
    config._reset_detection_cache()
    yield
    config._reset_detection_cache()


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *a, **k):
        return self._resp


def _patch_httpx(monkeypatch, resp):
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient(resp))


class TestEnvHelpers:
    def test_get_present_and_default(self, monkeypatch):
        monkeypatch.setenv("X_FOO", "bar")
        assert config.get("X_FOO") == "bar"
        assert config.get("X_MISSING", "def") == "def"

    def test_is_configured_true(self, monkeypatch):
        for k in ("LEMONSQUEEZY_WEBHOOK_SECRET", "LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_STORE_ID"):
            monkeypatch.setenv(k, "v")
        assert config.is_configured() is True

    def test_is_configured_false_when_missing(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", "v")
        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "v")
        monkeypatch.delenv("LEMONSQUEEZY_STORE_ID", raising=False)
        assert config.is_configured() is False

    def test_variant_to_tier_map(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_STARTER", "100")
        monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_CATALOG", "200")
        monkeypatch.delenv("LEMONSQUEEZY_VARIANT_ID_ALLACCESS", raising=False)
        assert config.variant_to_tier_map() == {"100": "starter", "200": "catalog"}

    def test_is_test_mode_default(self):
        assert config.is_test_mode() is (config.MODE == "test")


class TestFetchMode:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("LEMONSQUEEZY_API_KEY", raising=False)
        mode, err = config._fetch_lemonsqueezy_mode()
        assert mode is None and "missing" in err

    def test_test_mode_detected(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "k")
        _patch_httpx(monkeypatch, _FakeResp(200, {"data": [{"attributes": {"test_mode": True}}]}))
        assert config._fetch_lemonsqueezy_mode() == ("test", None)

    def test_live_mode_detected(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "k")
        _patch_httpx(monkeypatch, _FakeResp(200, {"data": [{"attributes": {"test_mode": False}}]}))
        assert config._fetch_lemonsqueezy_mode() == ("live", None)

    def test_http_error(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "k")
        _patch_httpx(monkeypatch, _FakeResp(403, {}))
        mode, err = config._fetch_lemonsqueezy_mode()
        assert mode is None and "403" in err

    def test_no_products(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "k")
        _patch_httpx(monkeypatch, _FakeResp(200, {"data": []}))
        mode, err = config._fetch_lemonsqueezy_mode()
        assert mode is None and "no products" in err

    def test_missing_test_mode_attr(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_KEY", "k")
        _patch_httpx(monkeypatch, _FakeResp(200, {"data": [{"attributes": {}}]}))
        mode, err = config._fetch_lemonsqueezy_mode()
        assert mode is None and "test_mode" in err


class TestDetectedMode:
    def test_success_cached(self, monkeypatch):
        calls = {"n": 0}

        def fake_fetch():
            calls["n"] += 1
            return "live", None

        monkeypatch.setattr(config, "_fetch_lemonsqueezy_mode", fake_fetch)
        assert config.detected_mode() == "live"
        assert config.detected_mode() == "live"  # cached
        assert calls["n"] == 1
        assert config.detection_error() is None

    def test_failure_falls_back_to_declared(self, monkeypatch):
        monkeypatch.setattr(config, "_fetch_lemonsqueezy_mode", lambda: (None, "boom"))
        assert config.detected_mode() == config.MODE
        assert config.detection_error() == "boom"
        assert config.key_mode_match() is True

    def test_key_mode_match_true_when_equal(self, monkeypatch):
        monkeypatch.setattr(config, "_fetch_lemonsqueezy_mode", lambda: (config.MODE, None))
        assert config.detected_mode() == config.MODE
        assert config.key_mode_match() is True

    def test_health_checks_shape(self, monkeypatch):
        monkeypatch.setattr(config, "_fetch_lemonsqueezy_mode", lambda: ("test", None))
        h = config.health_checks()
        assert set(h) >= {
            "webhook_secret_present",
            "api_key_present",
            "api_key_valid",
            "key_mode_match",
        }
        assert h["api_key_valid"] is True
