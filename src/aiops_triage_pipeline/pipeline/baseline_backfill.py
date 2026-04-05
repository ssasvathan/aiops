"""Baseline backfill: populate peak history and Redis cache from Prometheus range queries."""

import asyncio
import math
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.error import URLError

import structlog

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusHTTPClient,
)
from aiops_triage_pipeline.pipeline.baseline_store import (
    BaselineStoreClientProtocol,
    persist_metric_baselines,
)
from aiops_triage_pipeline.pipeline.stages.evidence import build_evidence_scope_key

_TOPIC_MESSAGES_IN_METRIC_KEY = "topic_messages_in_per_sec"

# Warn if intermediate ts_max_by_scope could consume substantial memory.
# At 1000 scopes × 8640 steps, the dict is roughly 1000 × 8640 × 56 ≈ 480 MB.
_LARGE_SCOPE_WARN_THRESHOLD = 500


class _PeakHistorySeedable(Protocol):
    """Minimal protocol for seeding peak history retention before the first scheduler cycle."""

    def seed(
        self,
        *,
        history_by_scope: dict[tuple[str, str, str], Sequence[float]],
    ) -> None: ...


async def backfill_baselines_from_prometheus(
    *,
    prometheus_client: PrometheusHTTPClient,
    metric_queries: dict[str, MetricQueryDefinition],
    redis_client: BaselineStoreClientProtocol,
    redis_ttl_policy: RedisTtlPolicyV1,
    peak_history_retention: _PeakHistorySeedable,
    lookback_days: int,
    step_seconds: int,
    timeout_seconds: int,
    total_timeout_seconds: int,
    logger: structlog.BoundLogger,
) -> None:
    """Backfill peak history and Redis baseline cache from Prometheus range queries.

    Queries all metrics over the configured lookback window. For each metric:
    - Layer A (Redis): persists the latest MAX value per scope for all metrics.
    - Layer B (in-memory deque): seeds topic_messages_in_per_sec time series per scope.

    Fails gracefully: per-metric errors are isolated (logged and skipped). If the total
    timeout is exceeded, backfill stops early with a warning and proceeds with whatever
    was collected.
    """
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=lookback_days)
    backfill_start = time.monotonic()

    metrics_succeeded = 0
    metrics_failed = 0
    total_data_points = 0

    # Layer A: track the most-recent (latest ts) MAX value per scope per metric.
    # dict[scope → dict[metric_key → (latest_ts, latest_max_val)]]
    # Using (ts, val) pairs ensures that when multiple series exist for the same scope
    # (e.g. different partitions), we pick the value at the most recent timestamp, not
    # the last series to be iterated.
    latest_by_scope_metric: dict[tuple[str, ...], dict[str, tuple[float, float]]] = {}
    # Layer B: ordered time-series MAX per scope (topic_messages_in_per_sec only)
    # key: (env, cluster_id, topic) 3-tuple; value: dict[timestamp -> max_value]
    ts_max_by_scope: dict[tuple[str, str, str], dict[float, float]] = {}

    all_metrics = list(metric_queries.items())
    total_metric_count = len(all_metrics)
    for metric_key, metric_defn in all_metrics:
        elapsed = time.monotonic() - backfill_start
        if elapsed > total_timeout_seconds:
            completed = metrics_succeeded + metrics_failed
            logger.warning(
                "baseline_backfill_total_timeout_exceeded",
                event_type="backfill.total_timeout_warning",
                elapsed_seconds=round(elapsed, 1),
                total_timeout_seconds=total_timeout_seconds,
                metrics_completed=completed,
                metrics_remaining=total_metric_count - completed,
            )
            break

        try:
            raw_records: list[dict[str, Any]] = await asyncio.to_thread(
                prometheus_client.query_range,
                metric_defn.metric_name,
                start,
                end,
                step_seconds,
                timeout=timeout_seconds,
            )
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning(
                "baseline_backfill_metric_query_failed",
                event_type="backfill.metric_query_warning",
                metric_key=metric_key,
                metric_name=metric_defn.metric_name,
                reason=str(exc),
            )
            metrics_failed += 1
            continue

        # Process each series record returned by query_range
        for record in raw_records:
            labels: dict[str, str] = record.get("labels", {})  # type: ignore[assignment]
            values: list[tuple[float, float]] = record.get("values", [])  # type: ignore[assignment]

            try:
                # build_evidence_scope_key normalizes labels internally — no double call needed
                scope = build_evidence_scope_key(labels, metric_key)
            except (ValueError, KeyError):
                continue  # skip malformed label sets — preserve UNKNOWN semantics

            # Layer A: track (latest_ts, max_val) per scope per metric across series.
            # This handles sparse data correctly: always use the most-recent timestamp's value,
            # and for series with identical last timestamps take the MAX.
            if values:
                last_ts, last_val = values[-1]
                if math.isfinite(last_val):
                    scope_metrics = latest_by_scope_metric.setdefault(scope, {})
                    existing = scope_metrics.get(metric_key)
                    if (
                        existing is None
                        or last_ts > existing[0]
                        or (last_ts == existing[0] and last_val > existing[1])
                    ):
                        scope_metrics[metric_key] = (last_ts, last_val)

            # Layer B: topic_messages_in_per_sec only, 3-tuple scopes
            if metric_key == _TOPIC_MESSAGES_IN_METRIC_KEY and len(scope) == 3:
                topic_scope: tuple[str, str, str] = scope  # type: ignore[assignment]
                ts_map = ts_max_by_scope.setdefault(topic_scope, {})
                for ts, val in values:
                    if math.isfinite(val):
                        existing_val = ts_map.get(ts)
                        if existing_val is None or val > existing_val:
                            ts_map[ts] = val

            total_data_points += len(values)

        metrics_succeeded += 1

    # Flatten Layer A (ts, val) pairs → just the value for persistence
    latest_max_by_scope_metric: dict[tuple[str, ...], dict[str, float]] = {
        scope: {mk: ts_val[1] for mk, ts_val in metrics.items()}
        for scope, metrics in latest_by_scope_metric.items()
    }

    # Persist Layer A: all metrics to Redis baseline cache
    if latest_max_by_scope_metric:
        persist_metric_baselines(
            redis_client=redis_client,
            source="prometheus",
            baselines_by_scope_metric=latest_max_by_scope_metric,
            redis_ttl_policy=redis_ttl_policy,
            computed_at=end,
        )

    # Warn if intermediate dict is large (high-cardinality environments)
    if len(ts_max_by_scope) >= _LARGE_SCOPE_WARN_THRESHOLD:
        estimated_intermediate_mb = len(ts_max_by_scope) * step_seconds * 56 // (1024 * 1024)
        logger.warning(
            "baseline_backfill_large_scope_count",
            event_type="backfill.large_scope_warning",
            scope_count=len(ts_max_by_scope),
            estimated_intermediate_mb=estimated_intermediate_mb,
        )

    # Seed Layer B: topic_messages_in_per_sec time series into peak history
    if ts_max_by_scope:
        history_by_scope: dict[tuple[str, str, str], Sequence[float]] = {
            scope: [ts_map[ts] for ts in sorted(ts_map)]
            for scope, ts_map in ts_max_by_scope.items()
        }
        peak_history_retention.seed(history_by_scope=history_by_scope)

        # Log memory footprint: float storage + per-deque Python object overhead (~200B each)
        total_values = sum(len(v) for v in history_by_scope.values())
        estimated_bytes = total_values * 8 + len(history_by_scope) * 200
        logger.info(
            "baseline_backfill_memory_footprint",
            event_type="backfill.memory_footprint",
            seeded_scope_count=len(history_by_scope),
            total_data_points=total_values,
            estimated_bytes=estimated_bytes,
        )

    wall_clock_seconds = round(time.monotonic() - backfill_start, 1)
    logger.info(
        "baseline_backfill_complete",
        event_type="backfill.complete",
        metrics_succeeded=metrics_succeeded,
        metrics_failed=metrics_failed,
        total_data_points=total_data_points,
        layer_a_scope_count=len(latest_max_by_scope_metric),
        layer_b_scope_count=len(ts_max_by_scope),
        wall_clock_seconds=wall_clock_seconds,
    )
