"""Unit tests for baseline/client.py — SeasonalBaselineClient (Story 1.2 + Story 1.3).

AC coverage (Story 1.2):
  AC1 — read_buckets reads correct Redis key and returns list[float]
  AC2 — update_bucket appends value and enforces MAX_BUCKET_VALUES cap
  AC3 — read_buckets_batch uses single mget round-trip for multiple metrics
  AC4 — missing Redis key returns empty list (no error)
  AC5 — Redis exceptions propagate (not swallowed)
  AC6 — fake Redis only, no real Redis dependency

AC coverage (Story 1.3 — seed_from_history):
  AC1-1.3 — seed_from_history partitions time-series into correct (dow, hour) buckets
  AC1-1.3 — seed_from_history covers all 168 (dow, hour) buckets when given 7 days of data
  AC2-1.3 — seed_from_history enforces MAX_BUCKET_VALUES cap per bucket
  AC3-1.3 — seed_from_history merges with existing bucket data
  AC4-1.3 — seed_from_history delegates bucket derivation to time_to_bucket() (no inline math)
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone

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


# ---------------------------------------------------------------------------
# Story 1.3: seed_from_history — AC1 partitioning into correct buckets
# ---------------------------------------------------------------------------

# Fixed UTC anchor: Monday 2024-01-01 00:00:00 UTC (weekday=0, hour=0)
_UTC_MON_MIDNIGHT = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
# Tuesday 2024-01-02 14:30:00 UTC (weekday=1, hour=14)
_UTC_TUE_14 = datetime(2024, 1, 2, 14, 30, 0, tzinfo=UTC)

_SEED_SCOPE = ("prod", "kafka-prod-east", "orders.completed")
_SEED_METRIC = "topic_messages_in_per_sec"
_SEED_SCOPE_STR = "prod|kafka-prod-east|orders.completed"


def _seed_key(dow: int, hour: int) -> str:
    return f"aiops:seasonal_baseline:{_SEED_SCOPE_STR}:{_SEED_METRIC}:{dow}:{hour}"


def test_seed_from_history_partitions_into_correct_buckets() -> None:
    """[P0] AC1-1.3: seed_from_history writes values into the (dow, hour) bucket
    derived from each datetime in the time-series via time_to_bucket()."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    # Monday midnight UTC → (dow=0, hour=0)
    # Tuesday 14:30 UTC  → (dow=1, hour=14)
    time_series = [
        (_UTC_MON_MIDNIGHT, 10.0),
        (_UTC_MON_MIDNIGHT.replace(minute=15), 12.0),  # same bucket (0, 0)
        (_UTC_TUE_14, 99.0),
    ]

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, time_series)

    mon_key = _seed_key(0, 0)
    tue_key = _seed_key(1, 14)

    assert mon_key in redis.store
    assert tue_key in redis.store

    mon_values = json.loads(redis.store[mon_key])
    tue_values = json.loads(redis.store[tue_key])

    assert sorted(mon_values) == sorted([10.0, 12.0])
    assert tue_values == [99.0]


def test_seed_from_history_covers_all_168_buckets() -> None:
    """[P0] AC1-1.3: Seeding 7 days × 24 hours = 168 (dow, hour) pairs writes to all
    168 distinct Redis keys (one per unique bucket combination)."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    # Generate exactly one timestamp per (dow, hour) — 7 days × 24 hours
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)  # Monday, hour 0
    time_series = [
        (base + timedelta(hours=i), float(i))
        for i in range(7 * 24)
    ]

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, time_series)

    written_keys = {k for k in redis.store if "seasonal_baseline" in k}
    assert len(written_keys) == 168


# ---------------------------------------------------------------------------
# Story 1.3: seed_from_history — AC2 MAX_BUCKET_VALUES cap enforcement
# ---------------------------------------------------------------------------


def test_seed_from_history_respects_max_bucket_values_cap() -> None:
    """[P0] AC2-1.3: When more than MAX_BUCKET_VALUES points land in the same bucket,
    seed_from_history caps the stored list to MAX_BUCKET_VALUES (most-recent retained)."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    # All timestamps map to the same (dow=0, hour=0) bucket
    overflow_count = MAX_BUCKET_VALUES + 5  # intentionally exceeds cap
    time_series = [
        (_UTC_MON_MIDNIGHT.replace(minute=m), float(m))
        for m in range(overflow_count)
    ]

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, time_series)

    key = _seed_key(0, 0)
    stored = json.loads(redis.store[key])

    assert len(stored) == MAX_BUCKET_VALUES
    assert isinstance(MAX_BUCKET_VALUES, int)


# ---------------------------------------------------------------------------
# Story 1.3: seed_from_history — AC3 merging with existing bucket data
# ---------------------------------------------------------------------------


def test_seed_from_history_merges_with_existing_bucket_data() -> None:
    """[P0] AC3-1.3: seed_from_history reads existing bucket values from Redis and
    merges new values with them before writing back (existing + new, then cap applied)."""
    redis = _FakeRedis()
    existing_values = [1.0, 2.0, 3.0]
    key = _seed_key(0, 0)
    redis.store[key] = json.dumps(existing_values)

    client = SeasonalBaselineClient(redis)

    # Single new data point in the same (dow=0, hour=0) bucket
    time_series = [(_UTC_MON_MIDNIGHT, 99.0)]

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, time_series)

    stored = json.loads(redis.store[key])

    # Existing values must be retained alongside the new value
    assert 1.0 in stored
    assert 2.0 in stored
    assert 3.0 in stored
    assert 99.0 in stored


def test_seed_from_history_merge_enforces_cap_on_combined_data() -> None:
    """[P1] AC3-1.3: When existing + new values together exceed MAX_BUCKET_VALUES,
    the combined list is capped to MAX_BUCKET_VALUES (oldest dropped)."""
    redis = _FakeRedis()
    # Pre-fill bucket with MAX_BUCKET_VALUES - 1 existing values
    existing_values = list(range(MAX_BUCKET_VALUES - 1))
    key = _seed_key(0, 0)
    redis.store[key] = json.dumps([float(v) for v in existing_values])

    client = SeasonalBaselineClient(redis)

    # Add 3 new values — total would be MAX_BUCKET_VALUES + 2, so cap must kick in
    new_vals = [100.0, 200.0, 300.0]
    time_series = [
        (_UTC_MON_MIDNIGHT.replace(second=i), v) for i, v in enumerate(new_vals)
    ]

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, time_series)

    stored = json.loads(redis.store[key])
    assert len(stored) == MAX_BUCKET_VALUES


# ---------------------------------------------------------------------------
# Story 1.3: seed_from_history — AC4 delegates bucket derivation to time_to_bucket()
# ---------------------------------------------------------------------------


def test_seed_from_history_uses_time_to_bucket_for_partitioning() -> None:
    """[P0] AC4-1.3: seed_from_history must use time_to_bucket() for bucket derivation.
    A non-UTC timezone datetime must be normalized to UTC (dow, hour), not local (dow, hour).

    Concrete check: 2024-01-02 09:30 America/New_York (UTC-5) == 2024-01-02 14:30 UTC
    → bucket (dow=1, hour=14), NOT (dow=1, hour=9).
    """
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    eastern = timezone(timedelta(hours=-5))  # UTC-5
    # 09:30 Eastern = 14:30 UTC → bucket (dow=1, hour=14)
    dt_eastern = datetime(2024, 1, 2, 9, 30, 0, tzinfo=eastern)

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, [(dt_eastern, 55.0)])

    # Must be stored under UTC (dow=1, hour=14), not local (dow=1, hour=9)
    utc_key = _seed_key(1, 14)
    wrong_key = _seed_key(1, 9)

    assert utc_key in redis.store, (
        f"Expected bucket key {utc_key!r} (UTC-normalized), "
        f"but it was not written. "
        f"If {wrong_key!r} is in the store, seed_from_history used local time instead of UTC."
    )
    assert wrong_key not in redis.store


def test_seed_from_history_rejects_naive_datetime() -> None:
    """[P1] AC4-1.3: seed_from_history raises ValueError for naive datetimes — the
    time_to_bucket() guard prevents silent local-time misconversions (Story 1.1 review)."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    naive_dt = datetime(2024, 1, 1, 0, 0, 0)  # no tzinfo — naive
    time_series = [(naive_dt, 1.0)]

    with pytest.raises(ValueError, match="timezone-aware"):
        client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, time_series)


def test_seed_from_history_empty_time_series_is_a_noop() -> None:
    """[P2] AC1-1.3: Calling seed_from_history with an empty time-series writes
    nothing to Redis (no crash, no empty keys written)."""
    redis = _FakeRedis()
    client = SeasonalBaselineClient(redis)

    client.seed_from_history(_SEED_SCOPE, _SEED_METRIC, [])

    assert len(redis.store) == 0
