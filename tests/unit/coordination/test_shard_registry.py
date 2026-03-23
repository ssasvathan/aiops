"""Unit tests for shard coordination: assignment, lease, and checkpoint primitives."""

from __future__ import annotations

import time

import pytest

from aiops_triage_pipeline.coordination.shard_registry import (
    RedisShardCoordinator,
    ShardLeaseStatus,
    assign_scopes_to_pod,
    build_shard_checkpoint_key,
    build_shard_lease_key,
)


# ── Fake Redis helpers ────────────────────────────────────────────────────────


class _FakeRedis:
    """In-memory Redis stub with NX and EX (TTL) support."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._expires_at: dict[str, float] = {}
        self.set_calls: list[dict[str, object]] = []

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, exp in self._expires_at.items() if exp <= now]
        for key in expired:
            self._values.pop(key, None)
            self._expires_at.pop(key, None)

    def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        self._purge_expired()
        if nx and name in self._values:
            return False
        self._values[name] = value
        if ex is not None:
            self._expires_at[name] = time.monotonic() + float(ex)
        self.set_calls.append({"name": name, "value": value, "nx": nx, "ex": ex})
        return True

    def get(self, name: str) -> str | None:
        self._purge_expired()
        return self._values.get(name)


class _ErrorRedis:
    """Raises on all operations to exercise fail-open paths."""

    def set(self, name: str, value: str, *, nx: bool, ex: int) -> bool:  # noqa: ARG002
        raise RuntimeError("redis unavailable")

    def get(self, name: str) -> str | None:  # noqa: ARG002
        raise RuntimeError("redis unavailable")


# ── Key builder tests ─────────────────────────────────────────────────────────


def test_shard_lease_key_format() -> None:
    assert build_shard_lease_key(0) == "aiops:shard:lease:0"
    assert build_shard_lease_key(7) == "aiops:shard:lease:7"


def test_shard_checkpoint_key_format() -> None:
    assert build_shard_checkpoint_key(2, 1700000000) == "aiops:shard:checkpoint:2:1700000000"
    assert build_shard_checkpoint_key(0, 0) == "aiops:shard:checkpoint:0:0"


# ── Deterministic assignment tests ────────────────────────────────────────────


def test_assign_scopes_is_stable_for_identical_inputs() -> None:
    scopes = [
        ("prod", "cluster-a", "orders"),
        ("prod", "cluster-a", "payments"),
        ("prod", "cluster-a", "inventory"),
        ("prod", "cluster-a", "billing"),
    ]
    active_pods = ["pod-a", "pod-b"]

    first = assign_scopes_to_pod(
        scopes=scopes, active_pod_ids=active_pods, shard_count=2, pod_id="pod-a"
    )
    second = assign_scopes_to_pod(
        scopes=scopes, active_pod_ids=active_pods, shard_count=2, pod_id="pod-a"
    )

    assert first == second
    assert set(first).issubset(set(scopes))


def test_assign_scopes_partitions_without_overlap_across_pods() -> None:
    scopes = [
        ("prod", "cluster-a", "orders"),
        ("prod", "cluster-a", "payments"),
        ("prod", "cluster-a", "inventory"),
        ("prod", "cluster-a", "billing"),
    ]
    active_pods = ["pod-a", "pod-b"]

    pod_a_scopes = set(
        assign_scopes_to_pod(
            scopes=scopes, active_pod_ids=active_pods, shard_count=2, pod_id="pod-a"
        )
    )
    pod_b_scopes = set(
        assign_scopes_to_pod(
            scopes=scopes, active_pod_ids=active_pods, shard_count=2, pod_id="pod-b"
        )
    )

    assert pod_a_scopes.isdisjoint(pod_b_scopes)
    assert pod_a_scopes | pod_b_scopes == set(scopes)


def test_assign_scopes_returns_all_when_pod_list_empty() -> None:
    scopes = [("dev", "c1", "t1"), ("dev", "c1", "t2")]
    result = assign_scopes_to_pod(
        scopes=scopes, active_pod_ids=[], shard_count=2, pod_id="pod-a"
    )
    assert result == scopes


def test_assign_scopes_returns_all_when_shard_count_zero() -> None:
    scopes = [("dev", "c1", "t1")]
    result = assign_scopes_to_pod(
        scopes=scopes, active_pod_ids=["pod-a"], shard_count=0, pod_id="pod-a"
    )
    assert result == scopes


def test_assign_scopes_single_pod_receives_all_scopes() -> None:
    scopes = [
        ("prod", "c", "t1"),
        ("prod", "c", "t2"),
        ("prod", "c", "t3"),
    ]
    result = assign_scopes_to_pod(
        scopes=scopes, active_pod_ids=["pod-solo"], shard_count=4, pod_id="pod-solo"
    )
    assert set(result) == set(scopes)


def test_assign_scopes_pod_id_not_in_members_receives_nothing() -> None:
    scopes = [("prod", "c", "t1"), ("prod", "c", "t2")]
    result = assign_scopes_to_pod(
        scopes=scopes,
        active_pod_ids=["pod-a", "pod-b"],
        shard_count=2,
        pod_id="pod-unknown",
    )
    assert result == []


# ── Lease acquisition tests ───────────────────────────────────────────────────


def test_lease_acquire_returns_acquired_on_first_call() -> None:
    redis_client = _FakeRedis()
    coordinator = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")

    outcome = coordinator.acquire_lease(shard_id=1, owner_id="pod-a", lease_ttl_seconds=300)

    assert outcome.status == ShardLeaseStatus.acquired
    assert outcome.shard_id == 1
    assert outcome.owner_id == "pod-a"
    assert outcome.ttl_seconds == 300


def test_lease_acquire_uses_set_nx_ex_with_correct_key() -> None:
    redis_client = _FakeRedis()
    coordinator = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")

    coordinator.acquire_lease(shard_id=3, owner_id="pod-a", lease_ttl_seconds=120)

    assert len(redis_client.set_calls) == 1
    call = redis_client.set_calls[0]
    assert call["name"] == "aiops:shard:lease:3"
    assert call["value"] == "pod-a"
    assert call["nx"] is True
    assert call["ex"] == 120


def test_lease_yields_when_another_pod_holds_it() -> None:
    redis_client = _FakeRedis()
    coordinator = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-b")

    # Pod-a acquires first
    redis_client.set("aiops:shard:lease:1", "pod-a", nx=False, ex=300)

    outcome = coordinator.acquire_lease(shard_id=1, owner_id="pod-b", lease_ttl_seconds=300)

    assert outcome.status == ShardLeaseStatus.yielded
    assert outcome.holder_id == "pod-a"


def test_lease_recovers_after_ttl_expiry() -> None:
    redis_client = _FakeRedis()
    coordinator = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-b")

    # Pod-a acquires with 1s TTL
    coordinator_a = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")
    first = coordinator_a.acquire_lease(shard_id=1, owner_id="pod-a", lease_ttl_seconds=1)
    assert first.status == ShardLeaseStatus.acquired

    # Pod-b yields immediately (lease still active)
    second = coordinator.acquire_lease(shard_id=1, owner_id="pod-b", lease_ttl_seconds=1)
    assert second.status == ShardLeaseStatus.yielded

    # After TTL expiry, pod-b can recover
    time.sleep(1.1)
    third = coordinator.acquire_lease(shard_id=1, owner_id="pod-b", lease_ttl_seconds=1)
    assert third.status == ShardLeaseStatus.acquired


def test_lease_acquire_fails_open_on_redis_error() -> None:
    redis_client = _ErrorRedis()
    coordinator = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")

    outcome = coordinator.acquire_lease(shard_id=0, owner_id="pod-a", lease_ttl_seconds=60)

    assert outcome.status == ShardLeaseStatus.fail_open
    assert outcome.reason is not None
    assert "redis" in outcome.reason.lower()


def test_lease_holder_id_decoded_from_bytes() -> None:
    class _BytesRedis(_FakeRedis):
        def get(self, name: str) -> bytes | None:  # type: ignore[override]
            val = super().get(name)
            return val.encode() if val is not None else None

    redis_client = _BytesRedis()
    coordinator = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-b")

    redis_client.set("aiops:shard:lease:2", "pod-a", nx=False, ex=300)

    outcome = coordinator.acquire_lease(shard_id=2, owner_id="pod-b", lease_ttl_seconds=300)
    assert outcome.status == ShardLeaseStatus.yielded
    assert outcome.holder_id == "pod-a"


# ── Checkpoint batching tests ─────────────────────────────────────────────────


def test_shard_checkpoint_key_matches_expected_format() -> None:
    key = build_shard_checkpoint_key(shard_id=0, interval_bucket=1700000300)
    assert key == "aiops:shard:checkpoint:0:1700000300"


def test_findings_cache_shard_checkpoint_write() -> None:
    from aiops_triage_pipeline.cache.findings_cache import set_shard_interval_checkpoint

    class _RecordingClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, key: str) -> str | None:
            return None

        def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
            self.calls.append({"key": key, "value": value, "ex": ex})
            return True

    client = _RecordingClient()
    set_shard_interval_checkpoint(
        redis_client=client,
        shard_id=2,
        interval_bucket=1700000600,
        ttl_seconds=660,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["key"] == "aiops:shard:checkpoint:2:1700000600"
    assert call["value"] == "1"
    assert call["ex"] == 660
