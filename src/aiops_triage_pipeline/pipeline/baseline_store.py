"""Redis baseline store helpers for FR3/FR4 baseline persistence and reuse."""

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger

BaselineScope = tuple[str, ...]
ScopeMetricPair = tuple[BaselineScope, str]


class BaselineStoreClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by baseline store helpers."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]:
        ...

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool | None:
        ...


def build_baseline_cache_key(
    *,
    source: str,
    scope: BaselineScope,
    metric_key: str,
) -> str:
    """Build baseline key aligned with D1 namespace and source segregation."""
    scope_key = "|".join(scope)
    return f"aiops:baseline:{source}:{scope_key}:{metric_key}"


def baseline_ttl_seconds(*, env: str, redis_ttl_policy: RedisTtlPolicyV1) -> int:
    """Read env-specific baseline TTL from redis-ttl-policy-v1.

    Baselines and peak profiles are both long-lived statistical context,
    so the peak-profile TTL is reused for baseline entries.
    """
    env_ttls = redis_ttl_policy.ttls_by_env.get(env)
    if env_ttls is None:
        fallback = min(v.peak_profile_seconds for v in redis_ttl_policy.ttls_by_env.values())
        get_logger("pipeline.baseline_store").warning(
            "baseline_ttl_env_not_found",
            event_type="cache.baseline_ttl_warning",
            env=env,
            fallback_ttl_seconds=fallback,
        )
        return fallback
    return env_ttls.peak_profile_seconds


def load_metric_baselines(
    *,
    redis_client: BaselineStoreClientProtocol,
    source: str,
    scope_metric_pairs: Sequence[ScopeMetricPair],
) -> dict[BaselineScope, dict[str, float]]:
    """Best-effort bulk load of baseline values by scope+metric."""
    logger = get_logger("pipeline.baseline_store")
    loaded: dict[BaselineScope, dict[str, float]] = defaultdict(dict)
    unique_pairs = sorted(set(scope_metric_pairs))
    if not unique_pairs:
        return {}

    keys = [
        build_baseline_cache_key(source=source, scope=scope, metric_key=metric_key)
        for scope, metric_key in unique_pairs
    ]
    try:
        values = _bulk_get_values(redis_client=redis_client, keys=keys)
    except Exception:
        logger.warning(
            "baseline_cache_bulk_read_failed",
            event_type="cache.baseline_read_warning",
            pair_count=len(unique_pairs),
        )
        return {}

    for (scope, metric_key), raw in zip(unique_pairs, values, strict=True):
        if raw is None:
            continue
        try:
            baseline_value = _deserialize_baseline(raw)
        except Exception:
            logger.warning(
                "baseline_cache_payload_invalid",
                event_type="cache.baseline_read_warning",
                scope=scope,
                metric_key=metric_key,
            )
            continue
        if not math.isfinite(baseline_value):
            logger.warning(
                "baseline_cache_payload_non_finite",
                event_type="cache.baseline_read_warning",
                scope=scope,
                metric_key=metric_key,
            )
            continue
        loaded[scope][metric_key] = baseline_value

    return {scope: dict(metric_map) for scope, metric_map in loaded.items()}


def persist_metric_baselines(
    *,
    redis_client: BaselineStoreClientProtocol,
    source: str,
    baselines_by_scope_metric: Mapping[BaselineScope, Mapping[str, float]],
    redis_ttl_policy: RedisTtlPolicyV1,
    computed_at: datetime | None = None,
) -> None:
    """Best-effort baseline persistence with env-specific TTL."""
    logger = get_logger("pipeline.baseline_store")
    effective_computed_at = computed_at or datetime.now(tz=UTC)
    for scope, baseline_by_metric in sorted(baselines_by_scope_metric.items()):
        if not scope:
            continue
        ttl_seconds = baseline_ttl_seconds(env=scope[0], redis_ttl_policy=redis_ttl_policy)
        for metric_key, baseline_value in sorted(baseline_by_metric.items()):
            if not math.isfinite(baseline_value):
                continue
            key = build_baseline_cache_key(
                source=source,
                scope=scope,
                metric_key=metric_key,
            )
            payload = _serialize_baseline(
                baseline_value=baseline_value,
                source=source,
                computed_at=effective_computed_at,
            )
            try:
                redis_client.set(key, payload, ex=ttl_seconds)
            except Exception:
                logger.warning(
                    "baseline_cache_write_failed",
                    event_type="cache.baseline_write_warning",
                    scope=scope,
                    metric_key=metric_key,
                )


def _serialize_baseline(
    *,
    baseline_value: float,
    source: str,
    computed_at: datetime,
) -> str:
    payload = {
        "baseline_value": baseline_value,
        "computed_at": computed_at.astimezone(UTC).isoformat(),
        "source": source,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _deserialize_baseline(raw: str | bytes) -> float:
    payload = _decode_payload(raw)
    parsed = json.loads(payload)
    if isinstance(parsed, dict):
        baseline_value = parsed.get("baseline_value")
        return float(baseline_value)
    return float(parsed)


def _decode_payload(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw


def _bulk_get_values(
    *,
    redis_client: BaselineStoreClientProtocol,
    keys: Sequence[str],
) -> Sequence[str | bytes | None]:
    mget = getattr(redis_client, "mget", None)
    if callable(mget):
        return list(mget(keys))
    return [redis_client.get(key) for key in keys]
