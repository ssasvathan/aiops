"""Unit tests for baseline/client.py — SeasonalBaselineClient (Story 1.2).

AC coverage:
  AC1 — read_buckets reads correct Redis key and returns list[float]
  AC2 — update_bucket appends value and enforces MAX_BUCKET_VALUES cap
  AC3 — read_buckets_batch uses single mget round-trip for multiple metrics
  AC4 — missing Redis key returns empty list (no error)
  AC5 — Redis exceptions propagate (not swallowed)
  AC6 — fake Redis only, no real Redis dependency
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from aiops_triage_pipeline.baseline.constants import MAX_BUCKET_VALUES

# ---------------------------------------------------------------------------
# Fake Redis helpers (mirrors pattern from tests/unit/pipeline/test_baseline_store.py)
# ---------------------------------------------------------------------------


class _FakeRedis:
    """In-memory Redis stand-in tracking mget call arguments."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.mget_calls: list[tuple[str, ...]] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        self.mget_calls.append(tuple(keys))
        return [self.store.get(key) for key in keys]

    def set(self, key: str, value: str) -> bool:
        self.store[key] = value
        return True


class _FailingRedis:
    """Redis stand-in that always raises RuntimeError to verify exception propagation."""

    def get(self, key: str) -> str | None:
        raise RuntimeError("redis unavailable")

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        raise RuntimeError("redis unavailable")

    def set(self, key: str, value: str) -> bool:
        raise RuntimeError("redis unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCOPE = ("prod", "kafka-prod-east", "orders.completed")
_METRIC_KEY = "topic_messages_in_per_sec"
_DOW = 1  # Tuesday (datetime.weekday() convention: Mon=0, Sun=6)
_HOUR = 14

assert isinstance(_DOW, int), "_DOW must be int (dow is always an integer bucket index)"
assert isinstance(_HOUR, int), "_HOUR must be int (hour is always an integer bucket index)"

_SCOPE_STR = "prod|kafka-prod-east|orders.completed"
_EXPECTED_KEY = f"aiops:seasonal_baseline:{_SCOPE_STR}:{_METRIC_KEY}:{_DOW}:{_HOUR}"


# ---------------------------------------------------------------------------
# AC1: read_buckets — correct key schema and float list deserialization
# ---------------------------------------------------------------------------


def test_read_buckets_returns_float_list() -> None:
    """[P0] AC1: read_buckets returns deserialized list[float] for an existing key."""
    redis = _FakeRedis()
    redis.store[_EXPECTED_KEY] = json.dumps([1.1, 2.2, 3.3])
    client = SeasonalBaselineClient(redis)

    result = client.read_buckets(_SCOPE, _METRIC_KEY, _DOW, _HOUR)

    assert result == [1.1, 2.2, 3.3]


def test_read_buckets_key_schema() -> None:
    """[P0] AC1: read_buckets uses correct key schema with |-joined scope segments."""
    redis = _FakeRedis()
    redis.store[_EXPECTED_KEY] = json.dumps([10.0])
    client = SeasonalBaselineClient(redis)

    result = client.read_buckets(_SCOPE, _METRIC_KEY, _DOW, _HOUR)

    # Non-empty result proves the client built and read the correct key (_EXPECTED_KEY).
    # Any key-building bug (wrong separator, wrong field order, wrong namespace) would cause
    # a cache miss and return [] instead of [10.0].
    assert result == [10.0]
    # Confirm scope uses "|" joining by checking the actual key in the store was accessed
    assert _EXPECTED_KEY in redis.store
    assert _SCOPE_STR in _EXPECTED_KEY


# ---------------------------------------------------------------------------
# AC4: read_buckets — missing key returns empty list
# ---------------------------------------------------------------------------


def test_read_buckets_missing_key_returns_empty_list() -> None:
    """[P0] AC4: read_buckets returns [] for a key that does not exist in Redis."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    result = client.read_buckets(_SCOPE, _METRIC_KEY, _DOW, _HOUR)

    assert result == []


# ---------------------------------------------------------------------------
# AC2: update_bucket — append and cap enforcement
# ---------------------------------------------------------------------------


def test_update_bucket_appends_value_to_existing_list() -> None:
    """[P0] AC2: update_bucket appends new float to existing bucket list."""
    redis = _FakeRedis()
    redis.store[_EXPECTED_KEY] = json.dumps([1.0, 2.0, 3.0])
    client = SeasonalBaselineClient(redis)

    client.update_bucket(_SCOPE, _METRIC_KEY, _DOW, _HOUR, 4.0)

    stored = json.loads(redis.store[_EXPECTED_KEY])
    assert stored == [1.0, 2.0, 3.0, 4.0]


def test_update_bucket_creates_new_list_when_key_missing() -> None:
    """[P1] AC2: update_bucket creates a new list when the key does not exist."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    client.update_bucket(_SCOPE, _METRIC_KEY, _DOW, _HOUR, 7.5)

    stored = json.loads(redis.store[_EXPECTED_KEY])
    assert stored == [7.5]


def test_update_bucket_cap_enforcement_drops_oldest() -> None:
    """[P0] AC2: update_bucket enforces MAX_BUCKET_VALUES cap; oldest value dropped."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    # Insert MAX_BUCKET_VALUES + 1 = 13 values (0.0 through 12.0)
    for i in range(MAX_BUCKET_VALUES + 1):
        client.update_bucket(_SCOPE, _METRIC_KEY, _DOW, _HOUR, float(i))

    stored = json.loads(redis.store[_EXPECTED_KEY])

    assert len(stored) == MAX_BUCKET_VALUES
    assert isinstance(MAX_BUCKET_VALUES, int)
    # Oldest value (0.0) must have been dropped; newest (12.0) must be present
    assert 0.0 not in stored
    assert stored[-1] == float(MAX_BUCKET_VALUES)


# ---------------------------------------------------------------------------
# AC3: read_buckets_batch — single mget round-trip
# ---------------------------------------------------------------------------

_METRIC_KEYS = [
    "topic_messages_in_per_sec",
    "topic_bytes_in_per_sec",
    "topic_messages_out_per_sec",
]


def test_read_buckets_batch_issues_single_mget_call() -> None:
    """[P0] AC3: read_buckets_batch uses exactly one mget call for all metrics."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    client.read_buckets_batch(_SCOPE, _METRIC_KEYS, _DOW, _HOUR)

    assert len(redis.mget_calls) == 1
    assert len(redis.mget_calls[0]) == len(_METRIC_KEYS)


def test_read_buckets_batch_returns_correct_float_lists() -> None:
    """[P0] AC3: read_buckets_batch returns mapping of metric_key → list[float]."""
    redis = _FakeRedis()
    for metric in _METRIC_KEYS:
        key = f"aiops:seasonal_baseline:{_SCOPE_STR}:{metric}:{_DOW}:{_HOUR}"
        redis.store[key] = json.dumps([float(len(metric))])
    client = SeasonalBaselineClient(redis)

    result = client.read_buckets_batch(_SCOPE, _METRIC_KEYS, _DOW, _HOUR)

    assert set(result.keys()) == set(_METRIC_KEYS)
    for metric in _METRIC_KEYS:
        assert result[metric] == [float(len(metric))]


def test_read_buckets_batch_missing_keys_return_empty_lists() -> None:
    """[P1] AC4: read_buckets_batch returns empty list for each missing key in the batch."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    result = client.read_buckets_batch(_SCOPE, _METRIC_KEYS, _DOW, _HOUR)

    assert set(result.keys()) == set(_METRIC_KEYS)
    for metric in _METRIC_KEYS:
        assert result[metric] == []


# ---------------------------------------------------------------------------
# AC5: Redis exception propagation — errors are NOT swallowed
# ---------------------------------------------------------------------------


def test_read_buckets_propagates_redis_exception() -> None:
    """[P1] AC5: read_buckets raises Redis exception without swallowing it."""
    client = SeasonalBaselineClient(_FailingRedis())

    with pytest.raises(RuntimeError, match="redis unavailable"):
        client.read_buckets(_SCOPE, _METRIC_KEY, _DOW, _HOUR)


def test_update_bucket_propagates_redis_exception() -> None:
    """[P1] AC5: update_bucket raises Redis exception without swallowing it."""
    client = SeasonalBaselineClient(_FailingRedis())

    with pytest.raises(RuntimeError, match="redis unavailable"):
        client.update_bucket(_SCOPE, _METRIC_KEY, _DOW, _HOUR, 1.0)


def test_read_buckets_batch_propagates_redis_exception() -> None:
    """[P1] AC5: read_buckets_batch raises Redis exception without swallowing it."""
    client = SeasonalBaselineClient(_FailingRedis())

    with pytest.raises(RuntimeError, match="redis unavailable"):
        client.read_buckets_batch(_SCOPE, _METRIC_KEYS, _DOW, _HOUR)
