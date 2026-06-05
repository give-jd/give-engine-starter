"""Tests per discovery LAN-only (guard indirizzi, InMemoryDiscovery)."""

from __future__ import annotations

import pytest

from core.shared.sync.discovery import (
    InMemoryDiscovery,
    Peer,
    _is_lan_address,
)
from core.shared.sync.exceptions import SyncError


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "127.0.0.1",
        "::1",
        "10.0.0.5",
        "192.168.1.20",
        "172.16.3.4",
        "fe80::1",  # link-local
    ],
)
def test_is_lan_accepts(host):
    assert _is_lan_address(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.216.34",  # public (example.com)
        "2001:4860:4860::8888",  # public IPv6
        "ollama.example.com",  # hostname non-IP
        "0.0.0.0",  # unspecified → bind su tutte le interfacce
        "::",  # unspecified IPv6
        "255.255.255.255",  # broadcast (reserved 240/4)
        "224.0.0.1",  # multicast
    ],
)
def test_is_lan_rejects(host):
    assert _is_lan_address(host) is False


def test_inmemory_advertise_browse_roundtrip():
    registry: list[Peer] = []
    a = InMemoryDiscovery(host="192.168.1.10", registry=registry)
    b = InMemoryDiscovery(host="192.168.1.11", registry=registry)
    a.advertise("desktop", 7777)
    peers = b.browse()
    assert Peer("desktop", "192.168.1.10", 7777) in peers


def test_inmemory_browse_empty():
    assert InMemoryDiscovery(host="127.0.0.1").browse() == []


def test_inmemory_rejects_public_host_on_init():
    with pytest.raises(SyncError):
        InMemoryDiscovery(host="8.8.8.8")


def test_inmemory_browse_filters_non_lan():
    # registry contaminato con un peer pubblico → browse lo esclude
    registry: list[Peer] = [Peer("rogue", "8.8.8.8", 9999)]
    d = InMemoryDiscovery(host="127.0.0.1", registry=registry)
    assert d.browse() == []
