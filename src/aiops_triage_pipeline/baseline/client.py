"""SeasonalBaselineClient — Redis I/O boundary for seasonal baseline data (D3)."""

import asyncio
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog

from aiops_triage_pipeline.baseline.computation import time_to_bucket
from aiops_triage_pipeline.baseline.constants import MAX_BUCKET_VALUES
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.pipeline.stages.evidence import build_evidence_scope_key

BaselineScope = tuple[str, ...]

_LAST_RECOMPUTE_KEY = "aiops:seasonal_baseline:last_recompute"


class SeasonalBaselineClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by SeasonalBaselineClient."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]:
        ...

    def set(self, key: str, value: str) -> bool | None:
        ...

    def pipeline(self) -> Any:
        ...


class SeasonalBaselineClient:
    """Encapsulates all Redis I/O for seasonal baseline storage.

    Key schema: aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}
    Value format: JSON float list, max MAX_BUCKET_VALUES items.
    """

    def __init__(self, redis_client: SeasonalBaselineClientProtocol) -> None:
        self._redis = redis_client

    def _build_key(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
    ) -> str:
        """Build the Redis key for a given scope, metric, and time bucket."""
        scope_str = "|".join(scope)
        return f"aiops:seasonal_baseline:{scope_str}:{metric_key}:{dow}:{hour}"

    def read_buckets(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
    ) -> list[float]:
        """Read historical float values for one bucket. Returns [] if key missing."""
        key = self._build_key(scope, metric_key, dow, hour)
        raw = self._redis.get(key)
        if raw is None:
            return []
        decoded = raw if isinstance(raw, str) else raw.decode()
        return json.loads(decoded)

    def read_buckets_batch(
        self,
        scope: BaselineScope,
        metric_keys: Sequence[str],
        dow: int,
        hour: int,
    ) -> dict[str, list[float]]:
        """Batch-read all metric buckets for one (scope, dow, hour) in a single mget."""
        keys = [self._build_key(scope, mk, dow, hour) for mk in metric_keys]
        raws = self._redis.mget(keys)
        result: dict[str, list[float]] = {}
        for metric_key, raw in zip(metric_keys, raws, strict=True):
            if raw is None:
                result[metric_key] = []
            else:
                decoded = raw if isinstance(raw, str) else raw.decode()
                result[metric_key] = json.loads(decoded)
        return result

    def update_bucket(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
        value: float,
    ) -> None:
        """Append value to bucket, enforcing MAX_BUCKET_VALUES cap (oldest dropped)."""
        existing = self.read_buckets(scope, metric_key, dow, hour)
        existing.append(value)
        if len(existing) > MAX_BUCKET_VALUES:
            existing = existing[-MAX_BUCKET_VALUES:]
        key = self._build_key(scope, metric_key, dow, hour)
        self._redis.set(key, json.dumps(existing))

    def get_last_recompute(self) -> str | None:
        """Return the stored UTC ISO timestamp of the last successful recomputation, or None."""
        raw = self._redis.get(_LAST_RECOMPUTE_KEY)
        if raw is None:
            return None
        if isinstance(raw, str):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            return raw.decode()
        return None

    def set_last_recompute(self, timestamp_iso: str) -> None:
        """Persist the UTC ISO timestamp of a successful recomputation."""
        self._redis.set(_LAST_RECOMPUTE_KEY, timestamp_iso)

    async def bulk_recompute(
        self,
        *,
        prometheus_client: Any,
        metric_queries: dict[str, MetricQueryDefinition],
        lookback_days: int,
        step_seconds: int,
        timeout_seconds: int,
        logger: structlog.BoundLogger,
    ) -> int:
        """Recompute all seasonal baseline buckets from Prometheus history.

        Phase 1: Build all key → JSON-list mappings entirely in memory.
        Phase 2: Bulk-write all keys via Redis pipeline (single round-trip).

        Returns:
            Total number of Redis keys written.
        """
        # Deferred import to break circular dependency:
        # baseline/client.py → pipeline/baseline_backfill.py → baseline/client.py
        # Moving _build_best_effort_scope to baseline/ would fix this but baseline_backfill.py
        # is out of scope for this story (Story 1.4 explicitly excludes it).
        from aiops_triage_pipeline.pipeline.baseline_backfill import _build_best_effort_scope

        end = datetime.now(tz=UTC)
        start = end - timedelta(days=lookback_days)

        # Phase 1: in-memory accumulation — no Redis writes during this phase
        key_data: dict[str, list[float]] = {}

        for metric_key, metric_defn in metric_queries.items():
            try:
                raw_records: list[dict[str, Any]] = await asyncio.to_thread(
                    prometheus_client.query_range,
                    metric_defn.metric_name,
                    start,
                    end,
                    step_seconds,
                    timeout=timeout_seconds,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "baseline_recompute_metric_query_failed",
                    event_type="recompute.metric_query_warning",
                    metric_key=metric_key,
                    metric_name=metric_defn.metric_name,
                )
                continue

            for record in raw_records:
                labels: dict[str, str] = record.get("labels", {})  # type: ignore[assignment]
                values: list[tuple[float, float]] = record.get("values", [])  # type: ignore[assignment]

                try:
                    scope = build_evidence_scope_key(labels, metric_key)
                except (ValueError, KeyError):
                    try:
                        scope = _build_best_effort_scope(labels)
                    except (ValueError, KeyError):
                        continue

                for ts_float, val in values:
                    if not math.isfinite(val):
                        continue
                    dt = datetime.fromtimestamp(ts_float, tz=UTC)
                    dow, hour = time_to_bucket(dt)
                    redis_key = self._build_key(scope, metric_key, dow, hour)
                    key_data.setdefault(redis_key, []).append(val)

        # Cap each bucket at MAX_BUCKET_VALUES (P2)
        bulk_payload: dict[str, str] = {}
        for key, values in key_data.items():
            capped = values[-MAX_BUCKET_VALUES:] if len(values) > MAX_BUCKET_VALUES else values
            bulk_payload[key] = json.dumps(capped)

        # Phase 2: bulk pipeline write (single round-trip)
        if bulk_payload:
            pipe = self._redis.pipeline()
            for key, value in bulk_payload.items():
                pipe.set(key, value)
            pipe.execute()

        return len(bulk_payload)

    def seed_from_history(
        self,
        scope: BaselineScope,
        metric_key: str,
        time_series: Sequence[tuple[datetime, float]],
    ) -> None:
        """Partition a time-series into 168 (dow, hour) buckets and write to Redis.

        Used during cold-start backfill to seed baselines from Prometheus range data.
        Each (dt, value) pair is bucketed by UTC (dow, hour) via time_to_bucket().
        Existing bucket contents are read first and merged; MAX_BUCKET_VALUES cap enforced.

        Args:
            scope: Baseline scope tuple identifying the metric series.
            metric_key: The metric identifier string.
            time_series: Sequence of (timezone-aware datetime, float) pairs.

        Raises:
            ValueError: If any datetime in time_series is naive (no tzinfo).
        """
        # Group new values by (dow, hour) bucket
        bucket_values: dict[tuple[int, int], list[float]] = {}
        for dt, value in time_series:
            bucket = time_to_bucket(dt)  # raises ValueError for naive datetimes
            bucket_values.setdefault(bucket, []).append(value)

        for (dow, hour), new_values in bucket_values.items():
            existing = self.read_buckets(scope, metric_key, dow, hour)
            merged = existing + new_values
            if len(merged) > MAX_BUCKET_VALUES:
                merged = merged[-MAX_BUCKET_VALUES:]
            key = self._build_key(scope, metric_key, dow, hour)
            self._redis.set(key, json.dumps(merged))
