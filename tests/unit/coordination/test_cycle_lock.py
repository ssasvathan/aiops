from __future__ import annotations

import pytest

from aiops_triage_pipeline.coordination.cycle_lock import RedisCycleLock
from aiops_triage_pipeline.coordination.protocol import CycleLockStatus


class _RecordingRedisLockClient:
    def __init__(
        self,
        *,
        set_result: bool = True,
        holder_value: str | bytes | None = None,
        raise_on_set: Exception | None = None,
    ) -> None:
        self._set_result = set_result
        self._holder_value = holder_value
        self._raise_on_set = raise_on_set
        self.set_calls: list[dict[str, object]] = []

    def set(self, name: str, value: str, *, nx: bool, ex: int) -> bool:
        if self._raise_on_set is not None:
            raise self._raise_on_set
        self.set_calls.append({"name": name, "value": value, "nx": nx, "ex": ex})
        if self._set_result:
            self._holder_value = value
        return self._set_result

    def get(self, name: str) -> str | bytes | None:  # noqa: ARG002 - Redis compatibility surface
        return self._holder_value


def test_cycle_lock_uses_set_nx_ex_with_interval_plus_margin() -> None:
    redis_client = _RecordingRedisLockClient(set_result=True)
    lock = RedisCycleLock(redis_client=redis_client, margin_seconds=90)

    outcome = lock.acquire(interval_seconds=300, owner_id="pod-a")

    assert redis_client.set_calls == [
        {"name": "aiops:lock:cycle", "value": "pod-a", "nx": True, "ex": 390}
    ]
    assert outcome.status == CycleLockStatus.acquired


def test_cycle_lock_returns_yielded_and_holder_for_contention() -> None:
    redis_client = _RecordingRedisLockClient(set_result=False, holder_value="pod-b")
    lock = RedisCycleLock(redis_client=redis_client, margin_seconds=60)

    outcome = lock.acquire(interval_seconds=300, owner_id="pod-a")

    assert outcome.status == CycleLockStatus.yielded
    assert outcome.holder_id == "pod-b"


def test_cycle_lock_decodes_bytes_holder() -> None:
    redis_client = _RecordingRedisLockClient(set_result=False, holder_value=b"pod-b")
    lock = RedisCycleLock(redis_client=redis_client, margin_seconds=60)

    outcome = lock.acquire(interval_seconds=300, owner_id="pod-a")

    assert outcome.status == CycleLockStatus.yielded
    assert outcome.holder_id == "pod-b"


def test_cycle_lock_returns_fail_open_on_redis_exception() -> None:
    redis_client = _RecordingRedisLockClient(raise_on_set=ConnectionError("redis down"))
    lock = RedisCycleLock(redis_client=redis_client, margin_seconds=60)

    outcome = lock.acquire(interval_seconds=300, owner_id="pod-a")

    assert outcome.status == CycleLockStatus.fail_open
    assert outcome.reason is not None
    assert "redis" in outcome.reason.lower()


def test_cycle_lock_margin_must_be_positive() -> None:
    with pytest.raises(ValueError, match="margin_seconds"):
        RedisCycleLock(redis_client=_RecordingRedisLockClient(), margin_seconds=0)


def test_cycle_lock_interval_must_be_positive() -> None:
    redis_client = _RecordingRedisLockClient(set_result=True)
    lock = RedisCycleLock(redis_client=redis_client, margin_seconds=60)

    with pytest.raises(ValueError, match="interval_seconds"):
        lock.acquire(interval_seconds=0, owner_id="pod-a")
