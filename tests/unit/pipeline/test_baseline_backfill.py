"""Unit tests for pipeline.baseline_backfill — backfill orchestration logic.

Story 1.3 additions:
  - _FakeSeasonalClient — captures seed_from_history() calls
  - test_backfill_calls_seed_from_history_for_each_scope_and_metric
  - test_backfill_converts_unix_timestamps_to_utc_datetimes
  - test_backfill_emits_baseline_deviation_backfill_seeded_log
  - test_backfill_seeds_all_metrics_not_just_topic_messages
  - Updates all existing call sites to pass seasonal_baseline_client=...
"""

import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.pipeline.baseline_backfill import (
    _build_best_effort_scope,
    backfill_baselines_from_prometheus,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl_by_key: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        return [self.store.get(key) for key in keys]

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttl_by_key[key] = ex
        return True


class _FakePeakRetention:
    def __init__(self) -> None:
        self.seeded: dict[tuple[str, str, str], Sequence[float]] | None = None
        self.seed_call_count = 0

    def seed(self, *, history_by_scope: dict[tuple[str, str, str], Sequence[float]]) -> None:
        self.seeded = dict(history_by_scope)
        self.seed_call_count += 1


class _FakeSeasonalClient:
    """Captures seed_from_history() calls for assertion in unit tests.

    Follows the same pattern as _FakePeakRetention — tracks all calls
    without touching Redis.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str, list[tuple[datetime, float]]]] = []

    def seed_from_history(
        self,
        scope: tuple[str, ...],
        metric_key: str,
        time_series: Sequence[tuple[datetime, float]],
    ) -> None:
        self.calls.append((scope, metric_key, list(time_series)))


def _ttl_policy() -> RedisTtlPolicyV1:
    ttls = RedisTtlsByEnv(
        evidence_window_seconds=600, peak_profile_seconds=3600, dedupe_seconds=300
    )
    return RedisTtlPolicyV1(
        ttls_by_env={"prod": ttls, "dev": ttls, "local": ttls, "uat": ttls}
    )


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
# Test: Layer A — Redis persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_persists_latest_max_to_redis_for_all_metrics() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec", "broker_bytes_in_per_sec")

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = [
        # topic_messages_in_per_sec — two time steps
        [_matrix_record(scope_labels, [(1000.0, 10.0), (1300.0, 15.0)])],
        # broker_bytes_in_per_sec — one step
        [_matrix_record(scope_labels, [(1000.0, 500.0)])],
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    # Layer A: latest value for each metric should be in Redis
    assert any("topic_messages_in_per_sec" in k for k in redis.store)
    assert any("broker_bytes_in_per_sec" in k for k in redis.store)
    # Latest max for topic_messages_in_per_sec is 15.0 (last step)
    msg_key = next(k for k in redis.store if "topic_messages_in_per_sec" in k)
    payload = json.loads(redis.store[msg_key])
    assert payload["baseline_value"] == 15.0


@pytest.mark.asyncio
async def test_backfill_seeds_peak_history_with_topic_messages_timeseries() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec", "broker_bytes_in_per_sec")

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = [
        [_matrix_record(scope_labels, [(1000.0, 10.0), (1300.0, 20.0), (1600.0, 15.0)])],
        # broker_bytes_in_per_sec — NOT seeded into Layer B
        [_matrix_record(scope_labels, [(1000.0, 500.0)])],
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    # Layer B: only topic_messages_in_per_sec seeded, ordered by timestamp
    assert retention.seed_call_count == 1
    assert retention.seeded is not None
    scope = ("prod", "c1", "orders")
    assert scope in retention.seeded
    assert list(retention.seeded[scope]) == [10.0, 20.0, 15.0]


@pytest.mark.asyncio
async def test_backfill_aggregates_max_across_partitions_per_timestamp() -> None:
    """Multiple series for same scope (different partitions) → MAX per timestamp step."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec")

    labels_p0 = {"env": "prod", "cluster_name": "c1", "topic": "orders", "partition": "0"}
    labels_p1 = {"env": "prod", "cluster_name": "c1", "topic": "orders", "partition": "1"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(labels_p0, [(1000.0, 10.0), (1300.0, 5.0)]),
        _matrix_record(labels_p1, [(1000.0, 20.0), (1300.0, 30.0)]),
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    assert retention.seeded is not None
    scope = ("prod", "c1", "orders")
    # At ts=1000: max(10, 20)=20; at ts=1300: max(5, 30)=30
    assert list(retention.seeded[scope]) == [20.0, 30.0]


@pytest.mark.asyncio
async def test_backfill_continues_on_individual_metric_failure() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec", "broker_bytes_in_per_sec")

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = [
        ValueError("simulated query failure"),
        [_matrix_record(scope_labels, [(1000.0, 500.0)])],
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    # Second metric succeeded despite first failing
    assert any("broker_bytes_in_per_sec" in k for k in redis.store)
    # topic_messages_in_per_sec failed, so no Layer B seed
    assert retention.seed_call_count == 0


@pytest.mark.asyncio
async def test_backfill_handles_empty_prometheus_response() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec")

    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = []

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    assert len(redis.store) == 0
    assert retention.seed_call_count == 0


@pytest.mark.asyncio
async def test_backfill_builds_correct_scopes_from_labels() -> None:
    """Scope construction uses 3-tuple for topic metrics, 4-tuple for lag metrics."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec", "consumer_group_lag")

    topic_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    lag_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders", "group": "my-group"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = [
        [_matrix_record(topic_labels, [(1000.0, 10.0)])],
        [_matrix_record(lag_labels, [(1000.0, 5.0)])],
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    # Verify 3-tuple scope key for topic metric
    assert any("prod|c1|orders:topic_messages_in_per_sec" in k for k in redis.store)
    # Verify 4-tuple scope key for lag metric
    assert any("prod|c1|my-group|orders:consumer_group_lag" in k for k in redis.store)


@pytest.mark.asyncio
async def test_backfill_respects_total_timeout() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    # Use 3 metrics so we can verify early exit
    queries = _make_metric_queries(
        "topic_messages_in_per_sec", "broker_bytes_in_per_sec", "broker_bytes_out_per_sec"
    )

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    call_count = 0

    def slow_query_range(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call sleeps so that total timeout is exceeded
        if call_count == 1:
            time.sleep(0.05)
        return [_matrix_record(scope_labels, [(1000.0, 1.0)])]

    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = slow_query_range
    mock_logger = MagicMock()
    seasonal = _FakeSeasonalClient()

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=0,  # instant timeout
        logger=mock_logger,
    )

    # Warning should have been logged about total timeout
    warning_calls = [
        call
        for call in mock_logger.warning.call_args_list
        if "total_timeout" in str(call)
    ]
    assert len(warning_calls) >= 1


@pytest.mark.asyncio
async def test_backfill_with_partial_prometheus_retention() -> None:
    """Prometheus returns only 7 days of data; backfill succeeds with available data."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec")

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    # 7 days at 300s = 2016 data points
    values = [(float(1000 + i * 300), float(i)) for i in range(2016)]
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [_matrix_record(scope_labels, values)]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    assert retention.seed_call_count == 1
    scope = ("prod", "c1", "orders")
    assert scope in retention.seeded
    assert len(list(retention.seeded[scope])) == 2016


@pytest.mark.asyncio
async def test_backfill_logs_memory_footprint_after_seeding() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec")

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(scope_labels, [(1000.0, 10.0), (1300.0, 20.0)]),
    ]
    mock_logger = MagicMock()

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=mock_logger,
    )

    # Verify memory footprint log event was emitted
    info_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert any("memory_footprint" in call for call in info_calls)


# ---------------------------------------------------------------------------
# Story 1.3: Layer C — seed_from_history integration with backfill
# ---------------------------------------------------------------------------

# Nine canonical contract metrics (all metrics that auto-discovery must cover)
_ALL_CONTRACT_METRICS = [
    "topic_messages_in_per_sec",
    "topic_messages_out_per_sec",
    "topic_bytes_in_per_sec",
    "topic_bytes_out_per_sec",
    "broker_bytes_in_per_sec",
    "broker_bytes_out_per_sec",
    "consumer_group_lag",
    "consumer_group_lag_seconds",
    "broker_under_replicated_partitions",
]


@pytest.mark.asyncio
async def test_backfill_calls_seed_from_history_for_each_scope_and_metric() -> None:
    """[P0] AC1-1.3: backfill calls seed_from_history() for every (scope, metric_key) pair
    discovered in the Prometheus response — both scope/metrics must be present in calls."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec", "broker_bytes_in_per_sec")

    scope_labels_a = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    scope_labels_b = {"env": "prod", "cluster_name": "c1", "topic": "payments"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = [
        # topic_messages_in_per_sec — two scopes
        [
            _matrix_record(scope_labels_a, [(1000.0, 10.0), (1300.0, 15.0)]),
            _matrix_record(scope_labels_b, [(1000.0, 20.0)]),
        ],
        # broker_bytes_in_per_sec — one scope
        [_matrix_record(scope_labels_a, [(1000.0, 500.0)])],
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    # Verify seed_from_history was called for all discovered (scope, metric_key) pairs
    called_pairs = {(call[0], call[1]) for call in seasonal.calls}

    scope_a = ("prod", "c1", "orders")
    scope_b = ("prod", "c1", "payments")

    assert (scope_a, "topic_messages_in_per_sec") in called_pairs
    assert (scope_b, "topic_messages_in_per_sec") in called_pairs
    assert (scope_a, "broker_bytes_in_per_sec") in called_pairs
    assert len(seasonal.calls) >= 3


@pytest.mark.asyncio
async def test_backfill_converts_unix_timestamps_to_utc_datetimes() -> None:
    """[P0] AC1-1.3: backfill converts Unix float timestamps from Prometheus to
    timezone-aware UTC datetime objects before passing to seed_from_history().

    Verifies that datetime.fromtimestamp(ts, tz=UTC) is used — NOT the naive
    datetime.utcfromtimestamp() which would produce a tz-naive datetime."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec")

    # Unix timestamps: 0 = 1970-01-01 00:00:00 UTC, 3600 = 1970-01-01 01:00:00 UTC
    ts_zero: float = 0.0
    ts_one_hour: float = 3600.0
    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = [
        _matrix_record(scope_labels, [(ts_zero, 10.0), (ts_one_hour, 20.0)])
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    assert len(seasonal.calls) >= 1
    _, _, time_series = seasonal.calls[0]
    assert len(time_series) >= 2

    # All datetimes passed to seed_from_history must be timezone-aware (UTC)
    for dt, _val in time_series:
        assert dt.tzinfo is not None, (
            f"Expected timezone-aware datetime but got naive: {dt!r}. "
            "backfill must use datetime.fromtimestamp(ts, tz=UTC), not utcfromtimestamp()."
        )
        # Verify UTC normalization: ts=0 must produce 1970-01-01 00:00 UTC
    epoch_dt = datetime.fromtimestamp(ts_zero, tz=UTC)
    ts_dts = [dt for dt, _ in time_series]
    assert epoch_dt in ts_dts


@pytest.mark.asyncio
async def test_backfill_emits_baseline_deviation_backfill_seeded_log() -> None:
    """[P0] AC4-1.3: After seeding, backfill emits the canonical structured log event
    'baseline_deviation_backfill_seeded' with scope_count, metric_count, bucket_count.

    Event name must be exactly 'baseline_deviation_backfill_seeded' (P6)."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries("topic_messages_in_per_sec", "broker_bytes_in_per_sec")

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = [
        [_matrix_record(scope_labels, [(1000.0, 10.0), (1300.0, 15.0)])],
        [_matrix_record(scope_labels, [(1000.0, 500.0)])],
    ]
    mock_logger = MagicMock()

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=mock_logger,
    )

    # The canonical log event name is 'baseline_deviation_backfill_seeded' (P6)
    all_info_calls = mock_logger.info.call_args_list
    seeded_calls = [
        call for call in all_info_calls
        if call.args and call.args[0] == "baseline_deviation_backfill_seeded"
    ]

    assert len(seeded_calls) == 1, (
        "Expected exactly one 'baseline_deviation_backfill_seeded' log event. "
        f"Found {len(seeded_calls)} matching calls out of {len(all_info_calls)} total. "
        "Check that baseline_backfill.py emits "
        "logger.info('baseline_deviation_backfill_seeded', ...)"
    )

    # Verify required fields are present in kwargs
    call_kwargs = seeded_calls[0].kwargs
    _ev = "baseline_deviation_backfill_seeded"
    assert "scope_count" in call_kwargs, f"Missing scope_count in {_ev}"
    assert "metric_count" in call_kwargs, f"Missing metric_count in {_ev}"
    assert "bucket_count" in call_kwargs, f"Missing bucket_count in {_ev}"


@pytest.mark.asyncio
async def test_backfill_seeds_all_metrics_not_just_topic_messages() -> None:
    """[P0] AC2-1.3: auto-discovery — backfill must call seed_from_history() for ALL
    contract metrics, not just topic_messages_in_per_sec (AC2 — FR22, FR23, NFR-S3).

    This test verifies Layer C treats all 9 metrics equally, unlike Layer B which
    only seeds topic_messages_in_per_sec."""
    redis = _FakeRedis()
    retention = _FakePeakRetention()
    seasonal = _FakeSeasonalClient()
    queries = _make_metric_queries(*_ALL_CONTRACT_METRICS)

    scope_labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    prometheus_client = MagicMock()
    # All 9 metrics return one data point each
    prometheus_client.query_range.return_value = [
        _matrix_record(scope_labels, [(1000.0, 1.0)])
    ]

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
        seasonal_baseline_client=seasonal,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=MagicMock(),
    )

    seeded_metric_keys = {call[1] for call in seasonal.calls}

    for metric in _ALL_CONTRACT_METRICS:
        assert metric in seeded_metric_keys, (
            f"seed_from_history() was NOT called for metric '{metric}'. "
            "Layer C backfill must process ALL contract metrics, "
            "not just topic_messages_in_per_sec."
        )


# ---------------------------------------------------------------------------
# _build_best_effort_scope — unit tests for fallback scope helper
# ---------------------------------------------------------------------------


def test_build_best_effort_scope_returns_env_cluster_topic() -> None:
    """[P0] Full label set with topic yields (env, cluster_name, topic) scope."""
    labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    result = _build_best_effort_scope(labels)
    assert result == ("prod", "c1", "orders")


def test_build_best_effort_scope_returns_env_cluster_group_topic() -> None:
    """[P0] Label set with group + topic yields (env, cluster_name, group, topic) scope."""
    labels = {"env": "prod", "cluster_name": "c1", "group": "my-group", "topic": "orders"}
    result = _build_best_effort_scope(labels)
    assert result == ("prod", "c1", "my-group", "orders")


def test_build_best_effort_scope_returns_env_cluster_group_no_topic() -> None:
    """[P1] Label set with group but no topic yields (env, cluster_name, group) scope."""
    labels = {"env": "prod", "cluster_name": "c1", "group": "my-group"}
    result = _build_best_effort_scope(labels)
    assert result == ("prod", "c1", "my-group")


def test_build_best_effort_scope_returns_env_cluster_only() -> None:
    """[P1] Minimal label set (env + cluster_name only) yields (env, cluster_name) scope."""
    labels = {"env": "prod", "cluster_name": "c1"}
    result = _build_best_effort_scope(labels)
    assert result == ("prod", "c1")


def test_build_best_effort_scope_raises_missing_env() -> None:
    """[P0] Missing 'env' label raises ValueError — minimal scope cannot be built."""
    labels = {"cluster_name": "c1", "topic": "orders"}
    with pytest.raises(ValueError, match="env.*cluster_name"):
        _build_best_effort_scope(labels)


def test_build_best_effort_scope_raises_missing_cluster_name() -> None:
    """[P0] Missing 'cluster_name' label raises ValueError — minimal scope cannot be built."""
    labels = {"env": "prod", "topic": "orders"}
    with pytest.raises(ValueError, match="env.*cluster_name"):
        _build_best_effort_scope(labels)


def test_build_best_effort_scope_raises_empty_labels() -> None:
    """[P1] Completely empty labels dict raises ValueError."""
    with pytest.raises(ValueError, match="env.*cluster_name"):
        _build_best_effort_scope({})


def test_build_best_effort_scope_returns_tuple() -> None:
    """[P1] Return type is tuple[str, ...] (not list or any other sequence)."""
    labels = {"env": "prod", "cluster_name": "c1", "topic": "orders"}
    result = _build_best_effort_scope(labels)
    assert isinstance(result, tuple)
