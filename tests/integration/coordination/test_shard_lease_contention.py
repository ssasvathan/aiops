"""Integration tests for shard lease contention and failed-holder recovery."""

from __future__ import annotations

import time

import pytest
import redis as redis_lib
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.coordination.shard_registry import (
    RedisShardCoordinator,
    ShardLeaseStatus,
)
from tests.integration.conftest import _is_environment_prereq_error, _wait_for_redis


@pytest.fixture(scope="module")
def redis_container():
    try:
        with DockerContainer("redis:7.2-alpine").with_exposed_ports(6379) as container:
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(6379))
            _wait_for_redis(host, port)
            yield container
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.fail(f"Docker/Redis unavailable: {exc}")
        raise


@pytest.fixture()
def redis_client(redis_container):
    client = redis_lib.Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )
    client.flushall()
    return client


def test_shard_lease_contention_yields_exactly_one_winner(redis_client) -> None:
    """Multi-pod contention results in one acquired and one yielded per shard lease interval."""
    coord_a = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")
    coord_b = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-b")

    outcome_a = coord_a.acquire_lease(shard_id=0, owner_id="pod-a", lease_ttl_seconds=30)
    outcome_b = coord_b.acquire_lease(shard_id=0, owner_id="pod-b", lease_ttl_seconds=30)

    statuses = {outcome_a.status, outcome_b.status}
    assert statuses == {ShardLeaseStatus.acquired, ShardLeaseStatus.yielded}

    if outcome_a.status == ShardLeaseStatus.acquired:
        assert outcome_b.holder_id == "pod-a"
    else:
        assert outcome_a.holder_id == "pod-b"


def test_shard_lease_recovery_occurs_after_holder_failure(redis_client) -> None:
    """After TTL expiry a new pod acquires the lease without manual intervention."""
    coord_a = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")
    coord_b = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-b")

    # Pod-a acquires with short TTL (simulates a pod that then "fails")
    first = coord_a.acquire_lease(shard_id=1, owner_id="pod-a", lease_ttl_seconds=2)
    assert first.status == ShardLeaseStatus.acquired

    # Pod-b cannot acquire while pod-a's lease is active
    before_expiry = coord_b.acquire_lease(shard_id=1, owner_id="pod-b", lease_ttl_seconds=2)
    assert before_expiry.status == ShardLeaseStatus.yielded

    # Wait for the lease to expire (D2: Redis is ephemeral, no persistent state dependency)
    time.sleep(2.5)

    # Pod-b recovers the shard after expiry — no manual intervention required
    recovered = coord_b.acquire_lease(shard_id=1, owner_id="pod-b", lease_ttl_seconds=30)
    assert recovered.status == ShardLeaseStatus.acquired


def test_shard_lease_independent_shards_can_be_held_by_different_pods(redis_client) -> None:
    """Different pods can hold different shard leases simultaneously."""
    coord_a = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")
    coord_b = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-b")

    shard_0_by_a = coord_a.acquire_lease(shard_id=0, owner_id="pod-a", lease_ttl_seconds=30)
    shard_1_by_b = coord_b.acquire_lease(shard_id=1, owner_id="pod-b", lease_ttl_seconds=30)

    assert shard_0_by_a.status == ShardLeaseStatus.acquired
    assert shard_1_by_b.status == ShardLeaseStatus.acquired


def test_shard_lease_renew_same_pod_fails_nx_semantics(redis_client) -> None:
    """Re-acquiring the same shard with NX semantics yields if lease is still active."""
    coord = RedisShardCoordinator(redis_client=redis_client, pod_id="pod-a")

    first = coord.acquire_lease(shard_id=2, owner_id="pod-a", lease_ttl_seconds=30)
    assert first.status == ShardLeaseStatus.acquired

    # Without explicit unlock, NX prevents immediate re-acquisition by the same pod
    second = coord.acquire_lease(shard_id=2, owner_id="pod-a", lease_ttl_seconds=30)
    assert second.status == ShardLeaseStatus.yielded
