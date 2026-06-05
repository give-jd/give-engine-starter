"""Gi.Ve Engine - Catalog update checker (client side).

Fetches the public manifest in the background, diffs it against what the
user has already seen, and exposes the result to the Cabina di Regia for
the welcome banner + /novita page.

Persistence:
  ~/.givengine/seen_catalog.json   what the user has already acknowledged
  ~/.givengine/manifest_cache.json last successful manifest download
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


GIVE_HOME = Path(os.environ.get("GIVE_HOME") or os.path.expanduser("~/.givengine"))
SEEN_FILE = GIVE_HOME / "seen_catalog.json"
CACHE_FILE = GIVE_HOME / "manifest_cache.json"

DEFAULT_MANIFEST_URL = "https://engine.givegroup.it/catalog/manifest.json"
FETCH_TIMEOUT_S = 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError, AttributeError):
        return None


def _days_between(later, earlier):
    return max(0, int((later - earlier).total_seconds() // 86400))


@dataclass
class UpdatesResult:
    has_updates: bool = False
    new_count: int = 0
    updated_count: int = 0
    days_since_last_visit: int = 0
    last_check_ts: Optional[str] = None
    new_recipes: list = field(default_factory=list)
    updated_recipes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class CatalogUpdateChecker:
    """Manifest fetcher + diff engine. Designed to be fire-and-forget on a
    background thread."""

    def __init__(self,
                 manifest_url: str = DEFAULT_MANIFEST_URL,
                 seen_file: Path = SEEN_FILE,
                 cache_file: Path = CACHE_FILE,
                 timeout_s: float = FETCH_TIMEOUT_S) -> None:
        self.manifest_url = manifest_url
        self.seen_file = Path(seen_file)
        self.cache_file = Path(cache_file)
        self.timeout_s = timeout_s
        self._fetch_lock = threading.Lock()

    def _load_cache(self):
        if not self.cache_file.exists():
            return None
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, manifest) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_seen(self) -> dict:
        if not self.seen_file.exists():
            return {"last_seen_at": None, "recipes_seen": {}}
        try:
            data = json.loads(self.seen_file.read_text(encoding="utf-8")) or {}
            data.setdefault("recipes_seen", {})
            return data
        except (json.JSONDecodeError, OSError):
            return {"last_seen_at": None, "recipes_seen": {}}

    def _save_seen(self, data: dict) -> None:
        self.seen_file.parent.mkdir(parents=True, exist_ok=True)
        self.seen_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def fetch(self):
        """Blocking fetch with bounded timeout. Returns the parsed manifest or
        None on any failure (network, timeout, JSON, HTTP non-2xx)."""
        try:
            import httpx  # type: ignore
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    r = client.get(self.manifest_url,
                                   headers={"Accept": "application/json"})
                if r.status_code != 200:
                    return None
                return r.json()
            except Exception:
                return None
        except ImportError:
            return self._fetch_stdlib()

    def _fetch_stdlib(self):
        try:
            import urllib.request
            req = urllib.request.Request(
                self.manifest_url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                if resp.status != 200:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def check_async(self) -> threading.Thread:
        """Fire-and-forget background fetch. Returns the thread (callers can
        ignore it). The cache file is updated only if the fetch succeeds."""
        def _run():
            with self._fetch_lock:
                manifest = self.fetch()
                if not manifest:
                    return
                existing = self._load_cache() or {}
                if existing.get("generated_at") == manifest.get("generated_at"):
                    return
                self._save_cache(manifest)

        t = threading.Thread(target=_run, name="catalog-update-fetch", daemon=True)
        t.start()
        return t

    def get_manifest(self, allow_fetch: bool = True):
        """Manifest completo del catalogo (cache → fetch → None).

        Usato dalla Cabina per mostrare TUTTE le ricette del catalogo
        (anche quelle non installate localmente, es. piano Starter).
        """
        manifest = self._load_cache()
        if manifest:
            return manifest
        if allow_fetch:
            manifest = self.fetch()
            if manifest:
                self._save_cache(manifest)
        return manifest

    def get_updates_since_last_seen(self) -> UpdatesResult:
        manifest = self._load_cache()
        if not manifest:
            return UpdatesResult()

        seen = self._load_seen()
        seen_map = seen.get("recipes_seen") or {}
        last_seen = _parse_iso(seen.get("last_seen_at"))
        now = datetime.now(timezone.utc)
        days = _days_between(now, last_seen) if last_seen else 0

        new_recipes, updated_recipes = [], []
        for r in manifest.get("recipes", []) or []:
            rid = r.get("id")
            ver = str(r.get("versione") or "1.0.0")
            if not rid:
                continue
            if rid not in seen_map:
                new_recipes.append(r)
            elif seen_map[rid] != ver:
                updated_recipes.append({**r, "versione_precedente": seen_map[rid]})

        return UpdatesResult(
            has_updates=bool(new_recipes or updated_recipes),
            new_count=len(new_recipes),
            updated_count=len(updated_recipes),
            days_since_last_visit=days,
            last_check_ts=manifest.get("generated_at"),
            new_recipes=new_recipes,
            updated_recipes=updated_recipes,
        )

    def mark_all_seen(self) -> bool:
        """Persist the current manifest's recipe id -> version map. Returns
        True iff a manifest was cached at the moment of the call."""
        manifest = self._load_cache()
        if not manifest:
            return False
        recipes_seen = {
            r.get("id"): str(r.get("versione") or "1.0.0")
            for r in (manifest.get("recipes") or [])
            if r.get("id")
        }
        self._save_seen({
            "last_seen_at": _now_iso(),
            "recipes_seen": recipes_seen,
        })
        return True


_singleton: Optional[CatalogUpdateChecker] = None


def checker() -> CatalogUpdateChecker:
    global _singleton
    if _singleton is None:
        _singleton = CatalogUpdateChecker()
    return _singleton
