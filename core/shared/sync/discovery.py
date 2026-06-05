"""Discovery dei peer — LAN-only (vincolo no-cloud, Punti 14/24).

Guard hard `_is_lan_address`: si accettano solo indirizzi loopback / privati
(RFC1918) / link-local. Qualsiasi IP pubblico è rifiutato → impossibile che il
sync "P2P locale" raggiunga un host su internet per misconfig.

`PeerDiscovery` è un Protocol: la logica applicativa dipende dall'interfaccia,
non dal trasporto. `InMemoryDiscovery` serve test e same-host. L'adapter mDNS
reale (`ZeroconfDiscovery`, dipendenza `zeroconf`) è follow-up documentato:
non si spedisce networking non testato.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Protocol

from core.shared.sync.exceptions import SyncError

_LOCALHOST_NAMES = frozenset({"localhost"})


@dataclass(frozen=True)
class Peer:
    """Un peer scoperto sulla rete locale.

    Attributes:
        name: nome del servizio annunciato.
        host: indirizzo (deve essere LAN: loopback/privato/link-local).
        port: porta TCP del servizio sync.
    """

    name: str
    host: str
    port: int


def _is_lan_address(host: str) -> bool:
    """True se host è loopback, privato (RFC1918) o link-local.

    Hostname non-IP diversi da "localhost" → False (il guard lavora su
    indirizzi risolti; per l'MVP i peer portano IP).

    Esclude esplicitamente unspecified (0.0.0.0 / ::), multicast e reserved
    (incl. broadcast 255.255.255.255 ∈ 240.0.0.0/4): un bind su 0.0.0.0
    esporrebbe il server su TUTTE le interfacce, non solo la LAN.
    """
    if host in _LOCALHOST_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    # Allow espliciti prima: loopback (::1 ∈ ::/8 è anche is_reserved) e
    # link-local non devono essere catturati dai reject sottostanti.
    if ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return False
    return ip.is_private


class PeerDiscovery(Protocol):
    """Interfaccia di discovery: la logica sync dipende da questo, non da mDNS."""

    def advertise(self, name: str, port: int) -> None:
        """Annuncia un servizio sync su questo host."""
        ...

    def browse(self) -> list[Peer]:
        """Restituisce i peer LAN attualmente visibili."""
        ...


class InMemoryDiscovery:
    """Discovery in-memory per test e same-host (nessuna rete).

    Più istanze possono condividere lo stesso `registry` (lista) per simulare
    peer che si vedono sulla stessa LAN.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        registry: list[Peer] | None = None,
    ) -> None:
        if not _is_lan_address(host):
            raise SyncError(
                f"Discovery ammette solo host LAN, ricevuto: {host}. "
                "Vincolo no-cloud (Punti 14/24)."
            )
        self._host = host
        self._registry: list[Peer] = registry if registry is not None else []

    def advertise(self, name: str, port: int) -> None:
        """Registra un servizio su questo host (rifiuta host non-LAN)."""
        self._registry.append(Peer(name=name, host=self._host, port=port))

    def browse(self) -> list[Peer]:
        """Peer visibili, filtrati di nuovo dal guard LAN (difesa in profondità)."""
        return [p for p in self._registry if _is_lan_address(p.host)]
