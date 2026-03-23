"""ATDD red-phase acceptance tests for Story 4.1 distributed cycle lock fail-open behavior."""

from __future__ import annotations

import inspect

import pytest

from aiops_triage_pipeline import __main__
from aiops_triage_pipeline.config.settings import Settings
from tests.atdd.fixtures.story_4_1_test_data import (
    RecordingRedisLockClient,
    build_settings_kwargs,
    extract_holder,
    load_module_or_fail,
    to_status_value,
)


def _load_cycle_lock_module() -> object:
    return load_module_or_fail("aiops_triage_pipeline.coordination.cycle_lock", pytest.fail)


def _build_cycle_lock(*, redis_client: object, margin_seconds: int = 60) -> object:
    module = _load_cycle_lock_module()

    if hasattr(module, "RedisCycleLock"):
        return module.RedisCycleLock(  # type: ignore[attr-defined]
            redis_client=redis_client,
            margin_seconds=margin_seconds,
        )
    if hasattr(module, "DistributedCycleLock"):
        return module.DistributedCycleLock(  # type: ignore[attr-defined]
            redis_client=redis_client,
            margin_seconds=margin_seconds,
        )

    pytest.fail(
        "Story 4.1 requires a lock implementation class named RedisCycleLock or "
        "DistributedCycleLock in aiops_triage_pipeline.coordination.cycle_lock"
    )


def _acquire_lock(lock: object, *, interval_seconds: int, owner_id: str) -> object:
    if hasattr(lock, "acquire"):
        return lock.acquire(interval_seconds=interval_seconds, owner_id=owner_id)  # type: ignore[attr-defined]
    if hasattr(lock, "try_acquire"):
        return lock.try_acquire(interval_seconds=interval_seconds, owner_id=owner_id)  # type: ignore[attr-defined]

    pytest.fail(
        "Story 4.1 lock class must expose acquire(...) or try_acquire(...) "
        "for scheduler coordination"
    )


def test_p0_settings_expose_distributed_cycle_lock_defaults_and_validation() -> None:
    """AC1/AC2: settings must expose feature flag + positive TTL margin controls."""
    settings = Settings(**build_settings_kwargs())

    assert hasattr(settings, "DISTRIBUTED_CYCLE_LOCK_ENABLED")
    assert getattr(settings, "DISTRIBUTED_CYCLE_LOCK_ENABLED") is False
    assert hasattr(settings, "CYCLE_LOCK_MARGIN_SECONDS")
    assert getattr(settings, "CYCLE_LOCK_MARGIN_SECONDS") > 0

    with pytest.raises(ValueError, match="CYCLE_LOCK_MARGIN_SECONDS"):
        Settings(**build_settings_kwargs(CYCLE_LOCK_MARGIN_SECONDS=0))


def test_p0_coordination_protocol_exposes_acquired_yielded_fail_open_statuses() -> None:
    """AC1/AC2: protocol surface must expose structured lock outcomes and statuses."""
    protocol = load_module_or_fail("aiops_triage_pipeline.coordination.protocol", pytest.fail)

    assert hasattr(protocol, "CycleLockOutcome")
    assert hasattr(protocol, "CycleLockStatus")

    status_values = {item.value for item in protocol.CycleLockStatus}  # type: ignore[attr-defined]
    assert {"acquired", "yielded", "fail_open"}.issubset(status_values)


def test_p0_cycle_lock_uses_set_nx_ex_with_interval_plus_margin_for_first_owner() -> None:
    """AC1: first contender should acquire Redis lock with SET NX EX and TTL margin."""
    redis_client = RecordingRedisLockClient(set_result=True)
    lock = _build_cycle_lock(redis_client=redis_client, margin_seconds=90)

    outcome = _acquire_lock(lock, interval_seconds=300, owner_id="pod-a")

    assert redis_client.set_calls[-1] == {
        "name": "aiops:lock:cycle",
        "value": "pod-a",
        "nx": True,
        "ex": 390,
    }
    assert to_status_value(outcome) == "acquired"


def test_p0_cycle_lock_returns_yielded_when_lock_is_held_by_another_pod() -> None:
    """AC1: non-holders must yield current interval and retry next tick."""
    redis_client = RecordingRedisLockClient(set_result=False, holder_value="pod-b")
    lock = _build_cycle_lock(redis_client=redis_client, margin_seconds=60)

    outcome = _acquire_lock(lock, interval_seconds=300, owner_id="pod-a")

    assert to_status_value(outcome) == "yielded"
    assert extract_holder(outcome) == "pod-b"


def test_p0_cycle_lock_returns_fail_open_when_redis_is_unavailable() -> None:
    """AC2: Redis failures must fail open with reason context, not halt execution."""
    redis_client = RecordingRedisLockClient(raise_on_set=ConnectionError("redis unavailable"))
    lock = _build_cycle_lock(redis_client=redis_client, margin_seconds=60)

    outcome = _acquire_lock(lock, interval_seconds=300, owner_id="pod-a")

    assert to_status_value(outcome) == "fail_open"
    reason = getattr(outcome, "reason", None) or getattr(outcome, "error", None)
    assert reason is not None
    assert "redis" in str(reason).lower()


def test_p1_metrics_surface_exposes_cycle_lock_counters_for_observability() -> None:
    """AC2: coordination observability counters should exist for acquired/yielded/fail-open."""
    from aiops_triage_pipeline.health import metrics

    assert hasattr(metrics, "record_cycle_lock_acquired")
    assert hasattr(metrics, "record_cycle_lock_yielded")
    assert hasattr(metrics, "record_cycle_lock_fail_open")


def test_p1_hot_path_scheduler_source_contains_feature_flag_and_fail_open_branching() -> None:
    """AC1/AC2: hot-path scheduler must explicitly gate on distributed lock outcomes."""
    source = inspect.getsource(__main__._hot_path_scheduler_loop)

    assert "DISTRIBUTED_CYCLE_LOCK_ENABLED" in source
    assert "yielded" in source.lower()
    assert "fail_open" in source.lower()
