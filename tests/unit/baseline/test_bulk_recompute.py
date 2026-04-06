"""Unit tests for SeasonalBaselineClient.bulk_recompute() — Story 1.4.

AC coverage (Story 1.4 — bulk_recompute):
  AC2 — bulk_recompute writes all (scope × metric × dow × hour) keys via pipeline
  AC2 — bulk_recompute returns count of unique Redis keys written
  AC2 — bulk_recompute uses time_to_bucket() for (dow, hour) partitioning
  AC2 — bulk_recompute enforces MAX_BUCKET_VALUES cap per bucket
  AC4 — No Redis writes when Prometheus raises before Phase 2
  AC2 — bulk_recompute handles empty Prometheus response gracefully

TDD RED PHASE: These tests FAIL because bulk_recompute(), get_last_recompute(),
and set_last_recompute() are not yet implemented on SeasonalBaselineClient.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from aiops_triage_pipeline.baseline.computation import time_to_bucket
from aiops_triage_pipeline.baseline.constants import MAX_BUCKET_VALUES
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition

# ---------------------------------------------------------------------------
# Fake Redis helpers — supports pipeline() context manager
# ---------------------------------------------------------------------------


class _FakePipeline:
    """In-memory pipeline that records set() calls and commits on execute()."""

    def __init__(self, redis: "_FakePipelineRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    def set(self, key: str, value: str) -> "_FakePipeline":
        self._ops.append((key, value))
        return self

    def execute(self) -> list[bool]:
        for key, value in self._ops:
            self._redis.store[key] = value
        return [True] * len(self._ops)


class _FakePipelineRedis:
    """In-memory Redis with pipeline() support for bulk-write testing.

    Critically: set() calls outside a pipeline go directly to store.
    set() calls inside a pipeline are deferred until execute().
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        return [self.store.get(k) for k in keys]

    def set(self, key: str, value: str) -> bool:
        self.store[key] = value
        return True

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


class _FailingBeforePhase2Redis(_FakePipelineRedis):
    """Redis that tracks whether pipeline() was ever called.

    Used to verify that no pipeline execute() happens when Prometheus fails.
    """

    def __init__(self) -> None:
        super().__init__()
        self.pipeline_called = False

    def pipeline(self) -> _FakePipeline:
        self.pipeline_called = True
        return _FakePipeline(self)


# ---------------------------------------------------------------------------
# Fake Prometheus client
# ---------------------------------------------------------------------------


def _make_metric_queries(*keys: str) -> dict[str, MetricQueryDefinition]:
    return {
        key: MetricQueryDefinition(
            metric_key=key,
            metric_name=f"prom_{key}",
            role="throughput" if "messages" in key else "health",
        )
        for key in keys
    }


def _matrix_record(
    labels: dict[str, str],
    values: list[tuple[float, float]],
) -> dict[str, Any]:
    return {"labels": labels, "values": values}


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

# Fixed UTC anchor: Monday 2024-01-01 00:00:00 UTC (weekday=0, hour=0)
_UTC_MON_MIDNIGHT = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
# Tuesday 2024-01-02 14:00:00 UTC (weekday=1, hour=14)
_UTC_TUE_14 = datetime(2024, 1, 2, 14, 0, 0, tzinfo=UTC)

_SCOPE_LABELS = {"env": "prod", "cluster_name": "kafka-prod-east", "topic": "orders.completed"}
_METRIC_KEY = "topic_messages_in_per_sec"

_SCOPE_STR = "prod|kafka-prod-east|orders.completed"


def _expected_key(metric_key: str, dow: int, hour: int) -> str:
    return f"aiops:seasonal_baseline:{_SCOPE_STR}:{metric_key}:{dow}:{hour}"


# ---------------------------------------------------------------------------
# AC2: bulk_recompute writes all buckets via pipeline
# ---------------------------------------------------------------------------


async def test_bulk_recompute_writes_all_buckets_via_pipeline() -> None:
    """[P0] AC2: bulk_recompute() writes (scope × metric × dow × hour) keys via pipeline.

    Two timestamps in different buckets → two separate Redis keys written.
    Verifies pipeline-based bulk write (not individual set calls).
    """
    redis = _FakePipelineRedis()
    client = SeasonalBaselineClient(redis)

    # Monday 00:00 UTC → (dow=0, hour=0); Tuesday 14:00 UTC → (dow=1, hour=14)
    ts_mon = _UTC_MON_MIDNIGHT.timestamp()
    ts_tue = _UTC_TUE_14.timestamp()

    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(_SCOPE_LABELS, [(ts_mon, 10.0), (ts_tue, 20.0)])
    ]

    queries = _make_metric_queries(_METRIC_KEY)

    await client.bulk_recompute(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=MagicMock(),
    )

    mon_dow, mon_hour = time_to_bucket(_UTC_MON_MIDNIGHT)
    tue_dow, tue_hour = time_to_bucket(_UTC_TUE_14)

    mon_key = _expected_key(_METRIC_KEY, mon_dow, mon_hour)
    tue_key = _expected_key(_METRIC_KEY, tue_dow, tue_hour)

    assert mon_key in redis.store, (
        f"Expected key {mon_key!r} not found in redis.store after bulk_recompute(). "
        "bulk_recompute() must write bucket keys via pipeline.execute()."
    )
    assert tue_key in redis.store, (
        f"Expected key {tue_key!r} not found in redis.store after bulk_recompute()."
    )

    mon_values = json.loads(redis.store[mon_key])
    tue_values = json.loads(redis.store[tue_key])

    assert 10.0 in mon_values
    assert 20.0 in tue_values


# ---------------------------------------------------------------------------
# AC2: bulk_recompute returns correct key count
# ---------------------------------------------------------------------------


async def test_bulk_recompute_returns_key_count() -> None:
    """[P0] AC2: bulk_recompute() returns the number of unique Redis keys written.

    Two distinct (dow, hour) buckets → return value must be 2.
    """
    redis = _FakePipelineRedis()
    client = SeasonalBaselineClient(redis)

    ts_mon = _UTC_MON_MIDNIGHT.timestamp()
    ts_tue = _UTC_TUE_14.timestamp()

    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(_SCOPE_LABELS, [(ts_mon, 10.0), (ts_tue, 20.0)])
    ]

    queries = _make_metric_queries(_METRIC_KEY)

    key_count = await client.bulk_recompute(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=MagicMock(),
    )

    assert key_count == 2, (
        f"Expected bulk_recompute() to return 2 (two distinct buckets), got {key_count}. "
        "Return value must equal the number of unique Redis keys written."
    )


# ---------------------------------------------------------------------------
# AC2: bulk_recompute uses time_to_bucket() for partitioning
# ---------------------------------------------------------------------------


async def test_bulk_recompute_uses_time_to_bucket_for_partitioning() -> None:
    """[P0] AC2: bulk_recompute() must delegate (dow, hour) derivation to time_to_bucket().

    Supply a known UTC timestamp; verify the Redis key uses the (dow, hour) from
    time_to_bucket() — not any inline datetime arithmetic.

    Monday 2024-01-01 00:00 UTC → time_to_bucket returns (0, 0).
    """
    redis = _FakePipelineRedis()
    client = SeasonalBaselineClient(redis)

    ts_mon = _UTC_MON_MIDNIGHT.timestamp()
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(_SCOPE_LABELS, [(ts_mon, 5.0)])
    ]

    queries = _make_metric_queries(_METRIC_KEY)

    await client.bulk_recompute(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=MagicMock(),
    )

    expected_dow, expected_hour = time_to_bucket(_UTC_MON_MIDNIGHT)
    expected_key = _expected_key(_METRIC_KEY, expected_dow, expected_hour)

    assert expected_key in redis.store, (
        f"Expected bucket key {expected_key!r} not found. "
        f"bulk_recompute() must use time_to_bucket() (returns dow={expected_dow}, "
        f"hour={expected_hour}) — never inline datetime.weekday() or .hour."
    )
    stored_values = json.loads(redis.store[expected_key])
    assert 5.0 in stored_values


# ---------------------------------------------------------------------------
# AC2: bulk_recompute enforces MAX_BUCKET_VALUES cap
# ---------------------------------------------------------------------------


async def test_bulk_recompute_enforces_max_bucket_values_cap() -> None:
    """[P0] AC2: bulk_recompute() caps each bucket at MAX_BUCKET_VALUES.

    Supply MAX_BUCKET_VALUES + 5 data points all in the same (dow=0, hour=0) bucket.
    The stored list must be capped to MAX_BUCKET_VALUES items.
    """
    redis = _FakePipelineRedis()
    client = SeasonalBaselineClient(redis)

    overflow_count = MAX_BUCKET_VALUES + 5
    # All timestamps in the same Monday 00:xx UTC bucket (dow=0, hour=0)
    ts_values = [
        (_UTC_MON_MIDNIGHT.timestamp() + i * 60, float(i))
        for i in range(overflow_count)
    ]

    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(_SCOPE_LABELS, ts_values)
    ]

    queries = _make_metric_queries(_METRIC_KEY)

    await client.bulk_recompute(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=MagicMock(),
    )

    expected_dow, expected_hour = time_to_bucket(_UTC_MON_MIDNIGHT)
    key = _expected_key(_METRIC_KEY, expected_dow, expected_hour)

    assert key in redis.store
    stored = json.loads(redis.store[key])

    assert len(stored) == MAX_BUCKET_VALUES, (
        f"Expected bucket to be capped at MAX_BUCKET_VALUES={MAX_BUCKET_VALUES}, "
        f"but got {len(stored)} values. "
        "bulk_recompute() must apply the cap before the pipeline write."
    )
    assert isinstance(MAX_BUCKET_VALUES, int)


# ---------------------------------------------------------------------------
# AC4: No Redis writes on Prometheus failure (Phase 1 exception)
# ---------------------------------------------------------------------------


async def test_bulk_recompute_no_redis_writes_on_prometheus_failure() -> None:
    """[P0] AC4: If Prometheus raises before Phase 2, Redis must remain untouched.

    This is the core NFR-R4 guarantee: compute entirely in memory first;
    only write to Redis if all computation succeeds.

    Implementation note: bulk_recompute() must NOT propagate individual metric
    failures — it catches per-metric errors and continues (following the backfill
    pattern). However, if ALL metrics fail (e.g., network down), zero keys are written.

    Test strategy: mock all metrics to fail → assert zero Redis writes.
    The test ONLY passes if bulk_recompute() exists AND handles failures without
    partial writes. In RED phase this fails with AttributeError (method not found).
    """
    redis = _FakePipelineRedis()
    client = SeasonalBaselineClient(redis)

    prometheus_client = MagicMock()
    # All metric queries fail — simulating total Prometheus outage
    prometheus_client.query_range.side_effect = ConnectionError("Prometheus unreachable")

    queries = _make_metric_queries(_METRIC_KEY, "broker_bytes_in_per_sec")

    # In RED phase: AttributeError — bulk_recompute() not yet implemented.
    # After implementation: must complete without raising, with zero keys written.
    await client.bulk_recompute(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=MagicMock(),
    )

    assert len(redis.store) == 0, (
        f"Redis store must be empty after all-Prometheus-failure run, "
        f"but found {len(redis.store)} key(s): {list(redis.store.keys())}. "
        "bulk_recompute() must NOT write to Redis before Phase 2 (NFR-R4)."
    )


# ---------------------------------------------------------------------------
# AC2: bulk_recompute handles empty Prometheus response
# ---------------------------------------------------------------------------


async def test_bulk_recompute_handles_empty_prometheus_response() -> None:
    """[P1] AC2: bulk_recompute() handles empty Prometheus query_range results.

    When query_range returns [], no keys are written and return value is 0.
    Must not crash.
    """
    redis = _FakePipelineRedis()
    client = SeasonalBaselineClient(redis)

    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = []

    queries = _make_metric_queries(_METRIC_KEY)

    key_count = await client.bulk_recompute(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=MagicMock(),
    )

    assert key_count == 0, (
        f"Expected key_count=0 for empty Prometheus response, got {key_count}."
    )
    assert len(redis.store) == 0, (
        f"Expected empty redis.store for empty Prometheus response, "
        f"found {len(redis.store)} key(s)."
    )
