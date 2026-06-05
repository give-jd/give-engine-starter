"""Tests end-to-end del SyncCoordinator (due peer in-memory che convergono)."""

from __future__ import annotations

from core.shared.sync.coordinator import SyncCoordinator
from core.shared.sync.envelope import seal_record

_KEY = b"\x07" * 32


class _InMemorySource:
    """SyncSource di riferimento: dict record_id -> (payload, updated_at)."""

    def __init__(self, records=None):
        self._records: dict[str, tuple[bytes, int]] = dict(records or {})

    def manifest_records(self):
        return [(rid, payload, ts) for rid, (payload, ts) in self._records.items()]

    def get_payload(self, record_id):
        return self._records[record_id]

    def apply_record(self, record_id, payload, updated_at):
        self._records[record_id] = (payload, updated_at)

    # helper di test
    def snapshot(self):
        return dict(self._records)


def _full_sync(src_a: _InMemorySource, src_b: _InMemorySource) -> None:
    """A invia a B ciò che B deve ricevere; un solo verso (A → B)."""
    a = SyncCoordinator(src_a, _KEY)
    b = SyncCoordinator(src_b, _KEY)
    plan = a.plan_against(b.local_manifest())  # dal punto di vista di A
    envelopes = a.export_envelopes(plan.to_send)
    b.import_envelopes(envelopes)


def test_new_record_propagates_a_to_b():
    a = _InMemorySource({"r1": (b"alfa", 100)})
    b = _InMemorySource({})
    _full_sync(a, b)
    assert b.snapshot()["r1"] == (b"alfa", 100)


def test_newer_record_overwrites_older():
    a = _InMemorySource({"r1": (b"new", 200)})
    b = _InMemorySource({"r1": (b"old", 100)})
    _full_sync(a, b)
    assert b.snapshot()["r1"] == (b"new", 200)


def test_older_incoming_does_not_overwrite_newer_local():
    a = _InMemorySource({"r1": (b"old", 100)})
    b = _InMemorySource({"r1": (b"newer", 300)})
    coord_a = SyncCoordinator(a, _KEY)
    coord_b = SyncCoordinator(b, _KEY)
    # forziamo A a esportare r1 e B a importarlo: B non deve regredire
    envelopes = coord_a.export_envelopes(["r1"])
    result = coord_b.import_envelopes(envelopes)
    assert b.snapshot()["r1"] == (b"newer", 300)
    assert result.skipped_older == ("r1",)
    assert result.applied == ()


def test_same_timestamp_diff_content_is_conflict_not_overwrite():
    a = _InMemorySource({"r1": (b"versioneA", 100)})
    b = _InMemorySource({"r1": (b"versioneB", 100)})
    coord_a = SyncCoordinator(a, _KEY)
    coord_b = SyncCoordinator(b, _KEY)
    envelopes = coord_a.export_envelopes(["r1"])
    result = coord_b.import_envelopes(envelopes)
    assert result.conflicts == ("r1",)
    assert b.snapshot()["r1"] == (b"versioneB", 100)  # NON sovrascritto


def test_tampered_envelope_counted_failed_not_applied():
    b = _InMemorySource({})
    coord_b = SyncCoordinator(b, _KEY)
    bad = bytearray(seal_record("r1", b"x", 1, _KEY))
    bad[-5] ^= 0xFF  # corrompe il JSON/base64
    result = coord_b.import_envelopes([bytes(bad)])
    assert result.failed_indices == (0,)
    assert "r1" not in b.snapshot()


def test_bidirectional_convergence():
    # A ha r1, B ha r2; dopo sync nei due versi entrambi hanno r1+r2
    a = _InMemorySource({"r1": (b"a-data", 10)})
    b = _InMemorySource({"r2": (b"b-data", 20)})
    _full_sync(a, b)  # A → B
    _full_sync(b, a)  # B → A
    assert set(a.snapshot()) == {"r1", "r2"}
    assert set(b.snapshot()) == {"r1", "r2"}
    assert a.snapshot()["r2"] == (b"b-data", 20)
    assert b.snapshot()["r1"] == (b"a-data", 10)


def test_intra_batch_older_does_not_overwrite_newer():
    # stesso batch: r1@200 poi r1@150 → il più vecchio NON deve vincere
    b = _InMemorySource({})
    coord = SyncCoordinator(b, _KEY)
    envs = [
        seal_record("r1", b"new", 200, _KEY),
        seal_record("r1", b"old", 150, _KEY),
    ]
    result = coord.import_envelopes(envs)
    assert b.snapshot()["r1"] == (b"new", 200)
    assert result.applied.count("r1") == 1  # 150 non riapplicato


def test_intra_batch_same_ts_diff_content_no_silent_overwrite():
    # stesso batch: r1@200(X) poi r1@200(Y) → il secondo è conflitto, non scrive
    b = _InMemorySource({})
    coord = SyncCoordinator(b, _KEY)
    envs = [
        seal_record("r1", b"X", 200, _KEY),
        seal_record("r1", b"Y", 200, _KEY),
    ]
    result = coord.import_envelopes(envs)
    assert b.snapshot()["r1"] == (b"X", 200)  # primo vince, secondo NON sovrascrive
    assert result.conflicts == ("r1",)


def test_export_uses_plan_to_send_only():
    a = _InMemorySource({"r1": (b"x", 5), "r2": (b"y", 5)})
    b = _InMemorySource({"r1": (b"x", 5)})  # B ha già r1 identico
    coord_a = SyncCoordinator(a, _KEY)
    plan = coord_a.plan_against(SyncCoordinator(b, _KEY).local_manifest())
    assert plan.to_send == ("r2",)  # r1 in-sync, solo r2 da inviare
