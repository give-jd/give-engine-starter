"""Adapter mDNS reale (zeroconf) per discovery LAN-only.

Implementa `PeerDiscovery` su mDNS/zeroconf, restando dietro l'interfaccia del
modulo: la logica applicativa non sa che il trasporto è zeroconf.

Design testabile: la logica dell'adapter (guard LAN-only, conversione in
`Peer`, ciclo di vita) è separata dal wiring zeroconf vero, isolato in
`_RealZeroconfBackend`. I test iniettano un `_Backend` fake → copertura piena
senza rete né dipendenza installata. `zeroconf` è importato lazy: il modulo si
importa anche dove la dipendenza non c'è.

Vincolo no-cloud (Punti 14/24): ogni peer scoperto passa per `_is_lan_address`;
indirizzi pubblici sono scartati a prescindere da cosa annuncia la rete.
"""

from __future__ import annotations

from typing import Protocol

from core.shared.sync.discovery import Peer, _is_lan_address
from core.shared.sync.exceptions import SyncError

SERVICE_TYPE = "_giveengine-sync._tcp.local."


def _peer_from_service(name: str, host: str, port: int) -> Peer | None:
    """Converte un servizio annunciato in Peer, applicando il guard LAN.

    Returns:
        Peer se host è LAN (loopback/privato/link-local), altrimenti None.
    """
    if not _is_lan_address(host):
        return None
    return Peer(name=name, host=host, port=port)


class _Backend(Protocol):
    """Wiring di trasporto, iniettabile. Restituisce tuple grezze (name, host, port)."""

    def register(self, service_type: str, name: str, host: str, port: int) -> None:
        """Annuncia un servizio sulla rete locale."""
        ...

    def browse(self, service_type: str, timeout: float) -> list[tuple[str, str, int]]:
        """Scopre i servizi del tipo dato; tuple (name, host, port)."""
        ...

    def close(self) -> None:
        """Rilascia le risorse di rete."""
        ...


class ZeroconfDiscovery:
    """Discovery mDNS LAN-only via zeroconf.

    Args:
        host: indirizzo locale su cui annunciare (deve essere LAN).
        instance_name: nome istanza del servizio annunciato.
        service_type: tipo servizio mDNS (default SERVICE_TYPE).
        backend: iniettabile per test; default = backend zeroconf reale.

    Raises:
        SyncError: host non-LAN, o dipendenza zeroconf assente (backend reale).
    """

    def __init__(
        self,
        host: str,
        instance_name: str = "give-sync",
        service_type: str = SERVICE_TYPE,
        *,
        backend: _Backend | None = None,
    ) -> None:
        if not _is_lan_address(host):
            raise SyncError(
                f"Discovery ammette solo host LAN, ricevuto: {host}. "
                "Vincolo no-cloud (Punti 14/24)."
            )
        self._host = host
        self._instance_name = instance_name
        self._service_type = service_type
        self._backend: _Backend = backend or _RealZeroconfBackend()

    def advertise(self, name: str, port: int) -> None:
        """Annuncia un servizio sync su questo host LAN."""
        self._backend.register(self._service_type, name, self._host, port)

    def browse(self, timeout: float = 2.0) -> list[Peer]:
        """Scopre i peer LAN; scarta qualsiasi indirizzo non-LAN."""
        found = self._backend.browse(self._service_type, timeout)
        peers = [_peer_from_service(n, h, p) for (n, h, p) in found]
        return [p for p in peers if p is not None]

    def close(self) -> None:
        """Rilascia le risorse mDNS."""
        self._backend.close()


class _RealZeroconfBackend:
    """Backend zeroconf reale. Importa la dipendenza lazy (mDNS via rete)."""

    def __init__(self) -> None:
        try:
            import zeroconf  # noqa: F401
        except ImportError as exc:
            raise SyncError(
                "dipendenza 'zeroconf' non installata: "
                "installa con 'pip install zeroconf' per l'adapter mDNS reale"
            ) from exc
        from zeroconf import Zeroconf

        self._zc = Zeroconf()
        self._registered: list[object] = []

    def register(self, service_type: str, name: str, host: str, port: int) -> None:
        import socket

        from zeroconf import ServiceInfo

        info = ServiceInfo(
            service_type,
            f"{name}.{service_type}",
            addresses=[socket.inet_aton(host)],
            port=port,
        )
        self._zc.register_service(info)
        self._registered.append(info)

    def browse(self, service_type: str, timeout: float) -> list[tuple[str, str, int]]:
        import socket
        import time

        from zeroconf import ServiceBrowser

        collected: list[tuple[str, str, int]] = []

        class _Listener:
            def add_service(self, zc, type_, name):  # noqa: ANN001
                info = zc.get_service_info(type_, name)
                if info and info.addresses:
                    host = socket.inet_ntoa(info.addresses[0])
                    collected.append((name, host, info.port))

            def update_service(self, zc, type_, name):  # noqa: ANN001
                pass

            def remove_service(self, zc, type_, name):  # noqa: ANN001
                pass

        browser = ServiceBrowser(self._zc, service_type, _Listener())
        time.sleep(timeout)
        browser.cancel()
        return collected

    def close(self) -> None:
        for info in self._registered:
            self._zc.unregister_service(info)
        self._zc.close()
