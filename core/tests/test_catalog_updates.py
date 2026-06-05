"""Test per core/catalog_updates.py (manifest fetch + diff novità catalogo)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from core import catalog_updates as cu


@pytest.fixture
def chk(tmp_path):
    return cu.CatalogUpdateChecker(
        manifest_url="https://example.test/manifest.json",
        seen_file=tmp_path / "seen.json",
        cache_file=tmp_path / "cache.json",
    )


class TestDateHelpers:
    def test_now_iso_format(self):
        s = cu._now_iso()
        assert s.endswith("Z") and "T" in s and len(s) == 20

    def test_parse_iso_z_suffix(self):
        dt = cu._parse_iso("2026-06-02T10:00:00Z")
        assert dt is not None and dt.tzinfo is not None

    def test_parse_iso_none_and_invalid(self):
        assert cu._parse_iso(None) is None
        assert cu._parse_iso("non-una-data") is None
        assert cu._parse_iso(12345) is None

    def test_days_between(self):
        now = datetime(2026, 6, 10, tzinfo=timezone.utc)
        earlier = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert cu._days_between(now, earlier) == 9
        assert cu._days_between(earlier, now) == 0  # clamp a 0


class TestResultDataclass:
    def test_to_dict(self):
        r = cu.UpdatesResult(has_updates=True, new_count=2)
        d = r.to_dict()
        assert d["has_updates"] is True and d["new_count"] == 2


class TestCacheSeenIO:
    def test_load_cache_missing(self, chk):
        assert chk._load_cache() is None

    def test_save_then_load_cache(self, chk):
        chk._save_cache({"generated_at": "x", "recipes": []})
        assert chk._load_cache()["generated_at"] == "x"

    def test_load_cache_corrupt(self, chk):
        chk.cache_file.parent.mkdir(parents=True, exist_ok=True)
        chk.cache_file.write_text("{not json", encoding="utf-8")
        assert chk._load_cache() is None

    def test_load_seen_missing_default(self, chk):
        s = chk._load_seen()
        assert s == {"last_seen_at": None, "recipes_seen": {}}

    def test_load_seen_corrupt(self, chk):
        chk.seen_file.parent.mkdir(parents=True, exist_ok=True)
        chk.seen_file.write_text("nope", encoding="utf-8")
        assert chk._load_seen()["recipes_seen"] == {}


class TestDiff:
    def test_no_cache_returns_empty(self, chk):
        assert chk.get_updates_since_last_seen().has_updates is False

    def test_detects_new_and_updated(self, chk):
        chk._save_cache(
            {
                "generated_at": "2026-06-02T00:00:00Z",
                "recipes": [
                    {"id": "a", "versione": "1.0.0"},
                    {"id": "b", "versione": "2.0.0"},
                    {"id": "c", "versione": "1.0.0"},
                ],
            }
        )
        last = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        chk._save_seen({"last_seen_at": last, "recipes_seen": {"a": "1.0.0", "b": "1.0.0"}})
        res = chk.get_updates_since_last_seen()
        assert res.new_count == 1  # c
        assert res.updated_count == 1  # b (1.0.0 -> 2.0.0)
        assert res.has_updates is True
        assert res.days_since_last_visit == 5
        assert res.updated_recipes[0]["versione_precedente"] == "1.0.0"

    def test_skips_recipe_without_id(self, chk):
        chk._save_cache({"recipes": [{"versione": "1.0.0"}, {"id": "x"}]})
        res = chk.get_updates_since_last_seen()
        assert res.new_count == 1  # solo x


class TestMarkSeen:
    def test_mark_all_seen_no_cache(self, chk):
        assert chk.mark_all_seen() is False

    def test_mark_all_seen_persists(self, chk):
        chk._save_cache({"recipes": [{"id": "a", "versione": "3.1.0"}]})
        assert chk.mark_all_seen() is True
        seen = json.loads(chk.seen_file.read_text(encoding="utf-8"))
        assert seen["recipes_seen"] == {"a": "3.1.0"}
        assert seen["last_seen_at"] is not None


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


class TestFetch:
    def test_fetch_success(self, chk, monkeypatch):
        monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient(_FakeResp(200, {"ok": 1})))
        assert chk.fetch() == {"ok": 1}

    def test_fetch_non_200(self, chk, monkeypatch):
        monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient(_FakeResp(503, {})))
        assert chk.fetch() is None

    def test_fetch_exception(self, chk, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("net")

        monkeypatch.setattr(httpx, "Client", boom)
        assert chk.fetch() is None


class TestCheckAsyncAndSingleton:
    def test_check_async_saves_cache(self, chk, monkeypatch):
        monkeypatch.setattr(chk, "fetch", lambda: {"generated_at": "g1", "recipes": []})
        t = chk.check_async()
        t.join(timeout=5)
        assert chk._load_cache()["generated_at"] == "g1"

    def test_check_async_skips_when_unchanged(self, chk, monkeypatch):
        chk._save_cache({"generated_at": "g1", "recipes": [{"id": "a"}]})
        monkeypatch.setattr(chk, "fetch", lambda: {"generated_at": "g1", "recipes": []})
        chk.check_async().join(timeout=5)
        assert chk._load_cache()["recipes"] == [{"id": "a"}]

    def test_check_async_noop_on_failed_fetch(self, chk, monkeypatch):
        monkeypatch.setattr(chk, "fetch", lambda: None)
        chk.check_async().join(timeout=5)
        assert chk._load_cache() is None

    def test_singleton(self):
        assert cu.checker() is cu.checker()
