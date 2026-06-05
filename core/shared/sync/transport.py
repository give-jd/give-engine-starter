"""Transport di rete LAN per il sync P2P (server HTTP + client pull).

Strato "wire" sopra il `SyncCoordinator`: muove manifest ed envelope fra due
istanze in esecuzione sulla rete locale. Modello **pull**: ogni dispositivo
espone un piccolo server HTTP e tira (pull) dal peer ciò che gli manca; per il
sync bidirezionale entrambi tirano l'uno dall'altro.

Sicurezza:
- bind solo su host LAN (`_is_lan_address`, esclude 0.0.0.0/multicast/reserved);
  host pubblico/unspecified → SyncError
- **auth a token derivato dalla master key**: `Authorization: Bearer <token>`,
  con `token = HMAC-SHA256(master_key, label)`, confronto in tempo costante.
  Gate l'accesso *attivo*: senza master key non si interroga il server.
- gli envelope restano E2E cifrati: il **contenuto** di clienti/documenti non è
  leggibile da terzi anche su rete ostile.
- tetti anti-DoS sul body della pull (Content-Length ≤ 1 MiB, ≤ 5000 id).

LIMITAZIONE NOTA (cleartext): il transport è HTTP in chiaro. Uno sniffer passivo
sulla LAN vede comunque (a) i **metadati** del manifest — record_id/hash/
timestamp — e (b) il bearer token, che è **statico e riusabile** (replay). Il
token però abilita solo la lettura dei metadati + il pull di envelope cifrati,
non il contenuto. Per LAN non fidate serve un follow-up: TLS con cert pinned dal
fingerprint della master key, oppure challenge-response (nonce HMAC single-use)
+ cifratura del body manifest. Da fare prima di esporre su reti non controllate.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import httpx

from core.shared.sync.coordinator import ImportResult, SyncCoordinator
from core.shared.sync.discovery import _is_lan_address
from core.shared.sync.exceptions import SyncError
from core.shared.sync.manifest import RecordMeta

_TOKEN_LABEL = b"give-sync-token-v1"
_MANIFEST_PATH = "/sync/manifest"
_PULL_PATH = "/sync/pull"
# Tetti contro DoS da risorsa su endpoint autenticato.
_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB per il body della pull request
_MAX_PULL_IDS = 5000  # numero massimo di record_id richiedibili in una pull
_MSG_BAD_REQUEST = "bad request"


def derive_sync_token(master_key: bytes) -> str:
    """Token di auth derivato deterministicamente dalla master key condivisa."""
    return hmac.new(master_key, _TOKEN_LABEL, hashlib.sha256).hexdigest()


class _Handler(BaseHTTPRequestHandler):
    """Handler HTTP: serve manifest e envelope, gated da token."""

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.sync_token}"  # type: ignore[attr-defined]
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, expected)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path != _MANIFEST_PATH:
            self._send_json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        coordinator: SyncCoordinator = self.server.coordinator  # type: ignore[attr-defined]
        manifest = coordinator.local_manifest()
        body = {
            rid: [meta.content_hash, meta.updated_at] for rid, meta in manifest.items()
        }
        self._send_json(200, {"manifest": body})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != _PULL_PATH:
            self._send_json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        # Cap del body: Content-Length mancante/non-positivo/oltre il tetto →
        # rifiuta senza leggere (no DoS da risorsa su endpoint autenticato).
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": _MSG_BAD_REQUEST})
            return
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._send_json(413, {"error": "payload too large"})
            return
        try:
            req = json.loads(self.rfile.read(length))
            raw_ids = req.get("ids", []) if isinstance(req, dict) else None
        except ValueError:
            self._send_json(400, {"error": _MSG_BAD_REQUEST})
            return
        # Solo liste di stringhe, sotto il cap (un id non-str avvelenerebbe il
        # source; troppi id = abuso).
        if not isinstance(raw_ids, list) or len(raw_ids) > _MAX_PULL_IDS:
            self._send_json(400, {"error": _MSG_BAD_REQUEST})
            return
        ids = [i for i in raw_ids if isinstance(i, str)]
        coordinator: SyncCoordinator = self.server.coordinator  # type: ignore[attr-defined]
        envelopes = coordinator.export_envelopes(ids)
        self._send_json(
            200, {"envelopes": [base64.b64encode(e).decode() for e in envelopes]}
        )

    def log_message(self, *args) -> None:  # silenzia il logging su stderr
        pass


class SyncServer:
    """Server HTTP LAN-only che espone un `SyncCoordinator` ai peer autenticati.

    Il server gira in un thread separato e fa solo letture sul coordinator
    (manifest + export envelope). Se il source è backed da SQLite, la connessione
    va aperta con `check_same_thread=False` per la lettura dal thread handler; le
    scritture (apply) avvengono lato client, non qui.

    Args:
        coordinator: coordinator locale che serve manifest/envelope.
        master_key: master key condivisa (deriva il token di auth).
        host: indirizzo di bind (deve essere LAN).
        port: porta (0 = effimera, leggibile da `.port` dopo lo start).
    """

    def __init__(
        self,
        coordinator: SyncCoordinator,
        master_key: bytes,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        if not _is_lan_address(host):
            raise SyncError(
                f"SyncServer ammette solo host LAN, ricevuto: {host}. "
                "Vincolo no-cloud (Punti 14/24)."
            )
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.coordinator = coordinator  # type: ignore[attr-defined]
        self._httpd.sync_token = derive_sync_token(master_key)  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


class SyncClient:
    """Client HTTP per il pull da un peer LAN autenticato."""

    def __init__(
        self, base_url: str, master_key: bytes, *, timeout: float = 5.0
    ) -> None:
        host = urlparse(base_url).hostname
        if not _is_lan_address(host or ""):
            raise SyncError(
                f"SyncClient ammette solo peer LAN, ricevuto: {host}. "
                "Vincolo no-cloud (Punti 14/24)."
            )
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {derive_sync_token(master_key)}"}
        self._timeout = timeout

    def get_manifest(self) -> dict[str, RecordMeta]:
        try:
            resp = httpx.get(
                f"{self._base}{_MANIFEST_PATH}",
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise SyncError(f"connessione al peer fallita: {exc}") from exc
        if resp.status_code != 200:
            raise SyncError(f"peer manifest HTTP {resp.status_code}")
        raw = resp.json().get("manifest", {})
        return {
            rid: RecordMeta(record_id=rid, content_hash=h, updated_at=ts)
            for rid, (h, ts) in raw.items()
        }

    def pull(self, record_ids) -> list[bytes]:
        ids = list(record_ids)
        if not ids:
            return []
        try:
            resp = httpx.post(
                f"{self._base}{_PULL_PATH}",
                headers=self._headers,
                json={"ids": ids},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise SyncError(f"pull dal peer fallito: {exc}") from exc
        if resp.status_code != 200:
            raise SyncError(f"peer pull HTTP {resp.status_code}")
        return [base64.b64decode(e) for e in resp.json().get("envelopes", [])]


def pull_sync(
    local: SyncCoordinator, peer_base_url: str, master_key: bytes
) -> ImportResult:
    """Esegue un pull unidirezionale dal peer: scarica ciò che manca e applica.

    Per il sync bidirezionale, ogni dispositivo chiama `pull_sync` verso l'altro.
    """
    client = SyncClient(peer_base_url, master_key)
    peer_manifest = client.get_manifest()
    plan = local.plan_against(peer_manifest)
    envelopes = client.pull(plan.to_request)
    return local.import_envelopes(envelopes)
