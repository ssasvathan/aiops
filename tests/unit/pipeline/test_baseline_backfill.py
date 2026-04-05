"""Unit tests for pipeline.baseline_backfill — backfill orchestration logic."""

import time
from collections.abc import Sequence
from typing import Any
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.pipeline.baseline_backfill import backfill_baselines_from_prometheus

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
    import json
    payload = json.loads(redis.store[msg_key])
    assert payload["baseline_value"] == 15.0


@pytest.mark.asyncio
async def test_backfill_seeds_peak_history_with_topic_messages_timeseries() -> None:
    redis = _FakeRedis()
    retention = _FakePeakRetention()
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
    queries = _make_metric_queries("topic_messages_in_per_sec")

    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = []

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
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

    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=queries,
        redis_client=redis,
        redis_ttl_policy=_ttl_policy(),
        peak_history_retention=retention,
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
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        total_timeout_seconds=300,
        logger=mock_logger,
    )

    # Verify memory footprint log event was emitted
    info_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert any("memory_footprint" in call for call in info_calls)
