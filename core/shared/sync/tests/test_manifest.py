"""Tests per manifest e diff_manifests (Last-Write-Wins, conflitti)."""

from __future__ import annotations

from core.shared.sync.manifest import build_manifest, diff_manifests


def test_build_manifest_hashes_and_keys():
    m = build_manifest([("r1", b"alfa", 100), ("r2", b"beta", 200)])
    assert set(m) == {"r1", "r2"}
    assert m["r1"].updated_at == 100
    assert len(m["r1"].content_hash) == 64  # sha256 hex


def test_diff_empty_both_in_sync():
    plan = diff_manifests({}, {})
    assert plan.in_sync is True
    assert plan.to_send == () and plan.to_request == () and plan.conflicts == ()


def test_diff_identical_in_sync():
    local = build_manifest([("r1", b"x", 1)])
    remote = build_manifest([("r1", b"x", 1)])
    plan = diff_manifests(local, remote)
    assert plan.in_sync is True


def test_diff_only_local_to_send():
    local = build_manifest([("r1", b"x", 1)])
    plan = diff_manifests(local, {})
    assert plan.to_send == ("r1",)
    assert plan.to_request == ()
    assert plan.in_sync is False


def test_diff_only_remote_to_request():
    remote = build_manifest([("r1", b"x", 1)])
    plan = diff_manifests({}, remote)
    assert plan.to_request == ("r1",)
    assert plan.to_send == ()


def test_diff_lww_local_newer_to_send():
    local = build_manifest([("r1", b"new", 200)])
    remote = build_manifest([("r1", b"old", 100)])
    plan = diff_manifests(local, remote)
    assert plan.to_send == ("r1",)
    assert plan.conflicts == ()


def test_diff_lww_remote_newer_to_request():
    local = build_manifest([("r1", b"old", 100)])
    remote = build_manifest([("r1", b"new", 200)])
    plan = diff_manifests(local, remote)
    assert plan.to_request == ("r1",)
    assert plan.conflicts == ()


def test_diff_same_timestamp_diff_hash_is_conflict():
    local = build_manifest([("r1", b"versioneA", 100)])
    remote = build_manifest([("r1", b"versioneB", 100)])
    plan = diff_manifests(local, remote)
    assert plan.conflicts == ("r1",)
    assert plan.to_send == () and plan.to_request == ()
    assert plan.in_sync is False


def test_diff_mixed_deterministic_order():
    local = build_manifest([("b", b"x", 5), ("a", b"y", 5), ("c", b"local", 9)])
    remote = build_manifest([("c", b"remote", 3)])
    plan = diff_manifests(local, remote)
    # a,b solo locali; c locale più recente → tutti to_send, ordinati
    assert plan.to_send == ("a", "b", "c")
