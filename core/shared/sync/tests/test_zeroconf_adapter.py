"""Tests per ZeroconfDiscovery (backend fake, zero rete/dep)."""

from __future__ import annotations

import pytest

from core.shared.sync.discovery import Peer
from core.shared.sync.exceptions import SyncError
from core.shared.sync.zeroconf_adapter import (
    SERVICE_TYPE,
    ZeroconfDiscovery,
    _peer_from_service,
    _RealZeroconfBackend,
)


class _FakeBackend:
    """Backend in-memory che registra le chiamate e restituisce tuple canned."""

    def __init__(self, browse_result=None):
        self.registered: list[tuple[str, str, str, int]] = []
        self.closed = False
        self._browse_result = browse_result or []

    def register(self, service_type, name, host, port):
        self.registered.append((service_type, name, host, port))

    def browse(self, service_type, timeout):
        return list(self._browse_result)

    def close(self):
        self.closed = True


def test_peer_from_service_lan_accepted():
    assert _peer_from_service("desktop", "192.168.1.5", 7777) == Peer(
        "desktop", "192.168.1.5", 7777
    )


def test_peer_from_service_public_rejected():
    assert _peer_from_service("rogue", "8.8.8.8", 7777) is None


def test_init_rejects_non_lan_host():
    with pytest.raises(SyncError):
        ZeroconfDiscovery(host="8.8.8.8", backend=_FakeBackend())


def test_advertise_delegates_to_backend():
    fake = _FakeBackend()
    d = ZeroconfDiscovery(host="192.168.1.5", backend=fake)
    d.advertise("desktop", 7777)
    assert fake.registered == [(SERVICE_TYPE, "desktop", "192.168.1.5", 7777)]


def test_browse_returns_lan_peers():
    fake = _FakeBackend(
        browse_result=[
            ("desktop", "192.168.1.6", 7777),
            ("mobile", "10.0.0.9", 7777),
        ]
    )
    d = ZeroconfDiscovery(host="192.168.1.5", backend=fake)
    peers = d.browse(timeout=0.0)
    assert Peer("desktop", "192.168.1.6", 7777) in peers
    assert Peer("mobile", "10.0.0.9", 7777) in peers


def test_browse_filters_public_addresses():
    # rete contaminata: un annuncio con IP pubblico → scartato (no-cloud)
    fake = _FakeBackend(
        browse_result=[
            ("ok", "192.168.1.6", 7777),
            ("evil", "8.8.8.8", 7777),
        ]
    )
    d = ZeroconfDiscovery(host="127.0.0.1", backend=fake)
    peers = d.browse(timeout=0.0)
    hosts = {p.host for p in peers}
    assert "8.8.8.8" not in hosts
    assert "192.168.1.6" in hosts


def test_close_delegates():
    fake = _FakeBackend()
    d = ZeroconfDiscovery(host="127.0.0.1", backend=fake)
    d.close()
    assert fake.closed is True


def test_real_backend_raises_clean_when_zeroconf_absent():
    # se zeroconf non è installato → SyncError azionabile, non ImportError grezzo
    try:
        import zeroconf  # noqa: F401
    except ImportError:
        with pytest.raises(SyncError) as exc:
            _RealZeroconfBackend()
        assert "zeroconf" in str(exc.value).lower()
    else:
        pytest.skip("zeroconf installato: percorso assenza-dipendenza non applicabile")
