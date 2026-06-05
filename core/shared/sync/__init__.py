"""Modulo sync P2P LAN-only E2E (no-cloud, Punti 14/24).

API pubblica:
- manifest: `RecordMeta`, `SyncPlan`, `build_manifest`, `diff_manifests`
- envelope: `seal_record`, `open_record`
- discovery: `Peer`, `PeerDiscovery`, `InMemoryDiscovery`
- zeroconf_adapter: `ZeroconfDiscovery`, `SERVICE_TYPE` (mDNS reale, dep lazy)
- coordinator: `SyncCoordinator`, `SyncSource`, `ImportResult`
- transport: `SyncServer`, `SyncClient`, `pull_sync`, `derive_sync_token`
- exceptions: `SyncError`
"""

from __future__ import annotations

from core.shared.sync.coordinator import (
    ImportResult,
    SyncCoordinator,
    SyncSource,
)
from core.shared.sync.discovery import (
    InMemoryDiscovery,
    Peer,
    PeerDiscovery,
)
from core.shared.sync.envelope import open_record, seal_record
from core.shared.sync.exceptions import SyncError
from core.shared.sync.manifest import (
    RecordMeta,
    SyncPlan,
    build_manifest,
    diff_manifests,
)
from core.shared.sync.transport import (
    SyncClient,
    SyncServer,
    derive_sync_token,
    pull_sync,
)
from core.shared.sync.zeroconf_adapter import SERVICE_TYPE, ZeroconfDiscovery

__all__ = [
    "RecordMeta",
    "SyncPlan",
    "build_manifest",
    "diff_manifests",
    "seal_record",
    "open_record",
    "Peer",
    "PeerDiscovery",
    "InMemoryDiscovery",
    "ZeroconfDiscovery",
    "SERVICE_TYPE",
    "SyncCoordinator",
    "SyncSource",
    "ImportResult",
    "SyncServer",
    "SyncClient",
    "pull_sync",
    "derive_sync_token",
    "SyncError",
]
