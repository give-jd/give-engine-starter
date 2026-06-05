"""Test per core/licensing.py (validator licenze Lemon Squeezy, client-side)."""

from __future__ import annotations

import pytest

from core import licensing as lic


@pytest.fixture(autouse=True)
def _lic_file(tmp_path, monkeypatch):
    """Isola LICENSE_FILE su tmp + resetta il validator singleton."""
    monkeypatch.setattr(lic, "LICENSE_FILE", tmp_path / "license.json")
    monkeypatch.setattr(lic, "_validator", None)
    yield


# ---------- helper puri -------------------------------------------------------
class TestHelpers:
    def test_mask_email_standard(self):
        assert lic._mask_email("mario.rossi@example.com") == "m***@e***.com"

    def test_mask_email_no_at(self):
        assert lic._mask_email("nope") == "***"

    def test_mask_email_domain_no_dot(self):
        assert lic._mask_email("a@localhost") == "a***@l***"

    def test_mask_key(self):
        assert lic._mask_key("ABCD-EFGH-IJKL-WXYZ").endswith("-WXYZ")
        assert lic._mask_key("") == ""

    def test_default_instance_name(self):
        assert lic._default_instance_name().startswith("givengine-")

    def test_resolve_tier(self, monkeypatch):
        monkeypatch.setattr(lic.config, "variant_to_tier_map", lambda: {"42": "catalog"})
        assert lic._resolve_tier(None) == "starter"
        assert lic._resolve_tier("42") == "catalog"
        assert lic._resolve_tier("999") == "starter"

    def test_translate_error(self):
        assert lic._translate_error(None, "fb") == "fb"
        assert "scaduta" in lic._translate_error("license_key_expired", "fb")
        assert lic._translate_error("unknown_code", "fb") == "fb"

    def test_status_to_dict(self):
        assert lic.LicenseStatus(valid=True, tier="catalog").to_dict()["tier"] == "catalog"


# ---------- persistence -------------------------------------------------------
class TestPersistence:
    def test_load_missing_returns_default(self):
        s = lic.load_persisted()
        assert s.valid is False and s.tier == "starter"
        assert "gratuito" in s.message

    def test_load_corrupt(self):
        lic.LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        lic.LICENSE_FILE.write_text("{bad", encoding="utf-8")
        s = lic.load_persisted()
        assert s.valid is False and "corrotto" in s.message

    def test_persist_roundtrip_and_full_key(self):
        st = lic.LicenseStatus(
            valid=True, tier="catalog", license_key_masked="····-WXYZ",
            instance_id="inst-1", validated_at="2026-06-02T00:00:00Z",
        )
        lic._persist(st, full_key="REAL-KEY-1234")
        assert lic._persisted_full_key() == "REAL-KEY-1234"
        loaded = lic.load_persisted()
        assert loaded.valid is True and loaded.tier == "catalog"
        assert loaded.instance_id == "inst-1"

    def test_persist_starter_not_valid(self):
        lic._persist(lic.LicenseStatus(valid=True, tier="starter"), full_key="K")
        assert lic.load_persisted().valid is False

    def test_clear_persisted_idempotent(self):
        lic._persist(lic.LicenseStatus(valid=True, tier="catalog"), full_key="K")
        lic.clear_persisted()
        assert lic._persisted_full_key() is None
        lic.clear_persisted()  # no error se già assente


# ---------- _parse ------------------------------------------------------------
class TestParse:
    def _v(self):
        return lic.LemonSqueezyLicenseValidator()

    def test_store_mismatch(self, monkeypatch):
        monkeypatch.setattr(lic.config, "get", lambda k, d="": "STORE_A" if "STORE" in k else d)
        body = {"meta": {"store_id": "STORE_B"}}
        st = self._v()._parse(body, "k")
        assert st.valid is False and st.error_code == "store_mismatch"

    def test_valid_active(self, monkeypatch):
        monkeypatch.setattr(lic.config, "get", lambda k, d="": "")
        monkeypatch.setattr(lic.config, "variant_to_tier_map", lambda: {"7": "all-access"})
        body = {
            "valid": True,
            "meta": {"variant_id": "7", "customer_email": "x@y.com", "test_mode": True},
            "license_key": {"status": "active", "expires_at": None},
            "instance": {"id": "i1"},
        }
        st = self._v()._parse(body, "ABCD-WXYZ")
        assert st.valid is True and st.tier == "all-access"
        assert st.instance_id == "i1" and st.test_mode is True

    def test_invalid_starter(self, monkeypatch):
        monkeypatch.setattr(lic.config, "get", lambda k, d="": "")
        monkeypatch.setattr(lic.config, "variant_to_tier_map", lambda: {})
        body = {"valid": False, "meta": {}, "error": "license_key_invalid"}
        st = self._v()._parse(body, "k")
        assert st.valid is False and st.tier == "starter"


# ---------- validate / activate / deactivate ---------------------------------
class TestValidate:
    def test_empty_key(self):
        st = lic.LemonSqueezyLicenseValidator().validate("")
        assert st.error_code == "empty"

    def test_httpx_missing(self, monkeypatch):
        v = lic.LemonSqueezyLicenseValidator()
        monkeypatch.setattr(v, "_post", lambda *a, **k: (500, {"error": "httpx_missing"}))
        assert v.validate("K").error_code == "httpx_missing"

    def test_upstream_5xx(self, monkeypatch):
        v = lic.LemonSqueezyLicenseValidator()
        monkeypatch.setattr(v, "_post", lambda *a, **k: (503, {}))
        assert v.validate("K").error_code == "upstream_unavailable"

    def test_empty_body(self, monkeypatch):
        v = lic.LemonSqueezyLicenseValidator()
        monkeypatch.setattr(v, "_post", lambda *a, **k: (200, {}))
        assert v.validate("K").error_code == "empty_response"

    def test_valid_and_cache(self, monkeypatch):
        monkeypatch.setattr(lic.config, "get", lambda k, d="": "")
        monkeypatch.setattr(lic.config, "variant_to_tier_map", lambda: {"7": "catalog"})
        v = lic.LemonSqueezyLicenseValidator()
        calls = {"n": 0}

        def fake_post(*a, **k):
            calls["n"] += 1
            return 200, {"valid": True, "meta": {"variant_id": "7"},
                         "license_key": {"status": "active"}}

        monkeypatch.setattr(v, "_post", fake_post)
        st1 = v.validate("K")
        st2 = v.validate("K")  # cache hit
        assert st1.valid is True and st2.valid is True
        assert calls["n"] == 1


class TestActivate:
    def test_empty(self):
        assert lic.LemonSqueezyLicenseValidator().activate("").error_code == "empty"

    def test_success_persists(self, monkeypatch):
        monkeypatch.setattr(lic.config, "get", lambda k, d="": "")
        monkeypatch.setattr(lic.config, "variant_to_tier_map", lambda: {"7": "catalog"})
        v = lic.LemonSqueezyLicenseValidator()
        monkeypatch.setattr(v, "_post", lambda *a, **k: (
            200,
            {"valid": True, "meta": {"variant_id": "7"},
             "license_key": {"status": "active"}, "instance": {"id": "i9"}},
        ))
        res = v.activate("KEY-1234")
        assert res.success is True and res.status.tier == "catalog"
        assert lic._persisted_full_key() == "KEY-1234"

    def test_failure(self, monkeypatch):
        monkeypatch.setattr(lic.config, "get", lambda k, d="": "")
        monkeypatch.setattr(lic.config, "variant_to_tier_map", lambda: {})
        v = lic.LemonSqueezyLicenseValidator()
        monkeypatch.setattr(
            v, "_post",
            lambda *a, **k: (200, {"valid": False, "meta": {}, "error": "license_key_invalid"}),
        )
        res = v.activate("BAD")
        assert res.success is False and res.error_code == "license_key_invalid"


class TestDeactivate:
    def test_no_creds_clears_and_true(self):
        assert lic.LemonSqueezyLicenseValidator().deactivate() is True

    def test_with_creds_posts(self, monkeypatch):
        v = lic.LemonSqueezyLicenseValidator()
        monkeypatch.setattr(v, "_post", lambda *a, **k: (200, {}))
        assert v.deactivate("K", "i1") is True


class TestModuleHelpers:
    def test_validator_singleton(self):
        assert lic.validator() is lic.validator()

    def test_current_status_not_valid(self):
        assert lic.current_status().valid is False

    def test_current_tier_default(self):
        assert lic.current_tier() == "starter"
