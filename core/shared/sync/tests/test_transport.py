"""Tests transport sync (server+client loopback reale, auth token, LAN guard)."""

from __future__ import annotations

import contextlib

import pytest

from core.shared.sync.coordinator import SyncCoordinator
from core.shared.sync.exceptions import SyncError
from core.shared.sync.transport import (
    SyncClient,
    SyncServer,
    derive_sync_token,
    pull_sync,
)

_KEY = b"\x0c" * 32
_OTHER_KEY = b"\x0d" * 32


class _InMemorySource:
    def __init__(self, records=None):
        self._records = dict(records or {})

    def manifest_records(self):
        return [(rid, p, ts) for rid, (p, ts) in self._records.items()]

    def get_payload(self, record_id):
        return self._records[record_id]

    def apply_record(self, record_id, payload, updated_at):
        self._records[record_id] = (payload, updated_at)

    def snapshot(self):
        return dict(self._records)


@contextlib.contextmanager
def _serving(source, key=_KEY):
    server = SyncServer(SyncCoordinator(source, key), key, host="127.0.0.1", port=0)
    server.start()
    try:
        yield f"http://127.0.0.1:{server.port}"
    finally:
        server.stop()


def test_derive_token_deterministic_and_key_dependent():
    assert derive_sync_token(_KEY) == derive_sync_token(_KEY)
    assert derive_sync_token(_KEY) != derive_sync_token(_OTHER_KEY)


def test_pull_sync_new_record():
    a = _InMemorySource({"r1": (b"alfa", 100)})
    b = _InMemorySource({})
    with _serving(a) as url_a:
        result = pull_sync(SyncCoordinator(b, _KEY), url_a, _KEY)
    assert result.applied == ("r1",)
    assert b.snapshot()["r1"] == (b"alfa", 100)


def test_pull_sync_bidirectional_convergence():
    a = _InMemorySource({"r1": (b"a-data", 10)})
    b = _InMemorySource({"r2": (b"b-data", 20)})
    with _serving(a) as url_a, _serving(b) as url_b:
        pull_sync(SyncCoordinator(b, _KEY), url_a, _KEY)  # B pulls from A
        pull_sync(SyncCoordinator(a, _KEY), url_b, _KEY)  # A pulls from B
    assert set(a.snapshot()) == {"r1", "r2"}
    assert set(b.snapshot()) == {"r1", "r2"}


def test_pull_only_requests_missing():
    a = _InMemorySource({"r1": (b"x", 5), "r2": (b"y", 5)})
    b = _InMemorySource({"r1": (b"x", 5)})  # B ha già r1 identico
    with _serving(a) as url_a:
        result = pull_sync(SyncCoordinator(b, _KEY), url_a, _KEY)
    assert result.applied == ("r2",)  # solo r2 mancante


def test_wrong_key_unauthorized():
    a = _InMemorySource({"r1": (b"x", 1)})
    with _serving(a, key=_KEY) as url_a:
        # client con key diversa → token diverso → 401 → SyncError
        with pytest.raises(SyncError):
            SyncClient(url_a, _OTHER_KEY).get_manifest()


def test_manifest_requires_auth():
    import httpx

    a = _InMemorySource({"r1": (b"x", 1)})
    with _serving(a) as url_a:
        # nessun header Authorization → 401
        resp = httpx.get(f"{url_a}/sync/manifest", timeout=5.0)
    assert resp.status_code == 401


def test_server_rejects_public_host():
    with pytest.raises(SyncError):
        SyncServer(SyncCoordinator(_InMemorySource(), _KEY), _KEY, host="8.8.8.8")


def test_client_rejects_public_host():
    with pytest.raises(SyncError):
        SyncClient("http://8.8.8.8:9999", _KEY)


def test_server_rejects_unspecified_host():
    # 0.0.0.0 = bind su tutte le interfacce → deve essere rifiutato
    with pytest.raises(SyncError):
        SyncServer(SyncCoordinator(_InMemorySource(), _KEY), _KEY, host="0.0.0.0")


def test_pull_rejects_oversized_body():
    import httpx

    from core.shared.sync.transport import derive_sync_token

    a = _InMemorySource({"r1": (b"x", 1)})
    with _serving(a) as url_a:
        headers = {"Authorization": f"Bearer {derive_sync_token(_KEY)}"}
        # body reale oltre il tetto da 1 MiB → 413 (cap anti-DoS)
        oversized = b'{"ids":["' + b"a" * (1024 * 1024 + 50) + b'"]}'
        resp = httpx.post(
            f"{url_a}/sync/pull", headers=headers, content=oversized, timeout=5.0
        )
    assert resp.status_code == 413
