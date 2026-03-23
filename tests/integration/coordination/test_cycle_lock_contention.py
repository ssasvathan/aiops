"""Integration tests for distributed cycle-lock contention semantics."""

from __future__ import annotations

import time

import pytest
import redis as redis_lib
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.coordination.cycle_lock import RedisCycleLock
from aiops_triage_pipeline.coordination.protocol import CycleLockStatus
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


def test_cycle_lock_contention_produces_one_winner_and_one_yielder(redis_client) -> None:
    lock_a = RedisCycleLock(redis_client=redis_client, margin_seconds=2)
    lock_b = RedisCycleLock(redis_client=redis_client, margin_seconds=2)

    outcome_a = lock_a.acquire(interval_seconds=1, owner_id="pod-a")
    outcome_b = lock_b.acquire(interval_seconds=1, owner_id="pod-b")

    assert {outcome_a.status, outcome_b.status} == {
        CycleLockStatus.acquired,
        CycleLockStatus.yielded,
    }
    if outcome_a.status == CycleLockStatus.acquired:
        assert outcome_b.holder_id == "pod-a"
    else:
        assert outcome_a.holder_id == "pod-b"


def test_cycle_lock_reacquires_after_ttl_expiry_without_explicit_unlock(redis_client) -> None:
    lock_a = RedisCycleLock(redis_client=redis_client, margin_seconds=1)
    lock_b = RedisCycleLock(redis_client=redis_client, margin_seconds=1)

    first = lock_a.acquire(interval_seconds=1, owner_id="pod-a")
    assert first.status == CycleLockStatus.acquired

    second = lock_b.acquire(interval_seconds=1, owner_id="pod-b")
    assert second.status == CycleLockStatus.yielded

    time.sleep(3)

    third = lock_b.acquire(interval_seconds=1, owner_id="pod-b")
    assert third.status == CycleLockStatus.acquired
