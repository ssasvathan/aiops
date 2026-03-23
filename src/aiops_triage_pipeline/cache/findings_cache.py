"""Redis adapter for per-interval anomaly findings caching."""

import json
from datetime import UTC, datetime
from typing import Callable, Protocol

from aiops_triage_pipeline.cache.evidence_window import evidence_window_ttl_seconds
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.coordination.shard_registry import (
    build_shard_checkpoint_key as _build_shard_checkpoint_key,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.anomaly import AnomalyFinding


class FindingsCacheClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by findings cache helpers."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool | None:
        ...


def build_interval_findings_cache_key(
    *,
    scope: tuple[str, ...],
    evaluation_time: datetime,
    interval_seconds: int = 300,
) -> str:
    """Build deterministic key for one scope's findings at one scheduler interval."""
    if len(scope) < 3:
        raise ValueError(f"scope must include at least (env, cluster_id, topic), got: {scope}")
    bucket_start_epoch = _interval_bucket_epoch_seconds(
        evaluation_time=evaluation_time,
        interval_seconds=interval_seconds,
    )
    scope_key = "|".join(scope)
    return f"evidence:findings|{scope_key}|{bucket_start_epoch}"


def build_legacy_interval_findings_cache_key(
    *,
    scope: tuple[str, ...],
    evaluation_time: datetime,
    interval_seconds: int = 300,
) -> str:
    """Build legacy key shape using the pre-cleanup format."""
    if len(scope) < 3:
        raise ValueError(f"scope must include at least (env, cluster_id, topic), got: {scope}")
    bucket_start_epoch = _interval_bucket_epoch_seconds(
        evaluation_time=evaluation_time,
        interval_seconds=interval_seconds,
    )
    scope_key = "|".join(scope)
    env, cluster_id = scope[0], scope[1]
    return f"evidence:findings:{env}|{cluster_id}|{scope_key}|{bucket_start_epoch}"


def interval_findings_ttl_seconds(*, env: str, redis_ttl_policy: RedisTtlPolicyV1) -> int:
    """Use redis-ttl-policy-v1 evidence-window TTL for per-interval findings."""
    return evidence_window_ttl_seconds(env=env, redis_ttl_policy=redis_ttl_policy)


def get_interval_findings(
    *,
    redis_client: FindingsCacheClientProtocol,
    scope: tuple[str, ...],
    evaluation_time: datetime,
    interval_seconds: int = 300,
) -> tuple[AnomalyFinding, ...] | None:
    """Load cached per-interval findings for one scope."""
    raw = redis_client.get(
        build_interval_findings_cache_key(
            scope=scope,
            evaluation_time=evaluation_time,
            interval_seconds=interval_seconds,
        )
    )
    if raw is None:
        raw = redis_client.get(
            build_legacy_interval_findings_cache_key(
                scope=scope,
                evaluation_time=evaluation_time,
                interval_seconds=interval_seconds,
            )
        )
    if raw is None:
        return None
    if isinstance(raw, bytes):
        payload = raw.decode("utf-8")
    else:
        payload = raw
    return _deserialize_findings(payload)


def set_interval_findings(
    *,
    redis_client: FindingsCacheClientProtocol,
    scope: tuple[str, ...],
    env: str,
    evaluation_time: datetime,
    findings: tuple[AnomalyFinding, ...],
    redis_ttl_policy: RedisTtlPolicyV1,
    interval_seconds: int = 300,
) -> None:
    """Store one scope's per-interval findings with env-specific TTL."""
    ttl = interval_findings_ttl_seconds(env=env, redis_ttl_policy=redis_ttl_policy)
    redis_client.set(
        build_interval_findings_cache_key(
            scope=scope,
            evaluation_time=evaluation_time,
            interval_seconds=interval_seconds,
        ),
        _serialize_findings(findings),
        ex=ttl,
    )


def get_or_compute_interval_findings(
    *,
    redis_client: FindingsCacheClientProtocol,
    scope: tuple[str, ...],
    evaluation_time: datetime,
    redis_ttl_policy: RedisTtlPolicyV1,
    compute_findings: Callable[[], tuple[AnomalyFinding, ...]],
    interval_seconds: int = 300,
) -> tuple[AnomalyFinding, ...]:
    """Read-through helper for per-interval findings with warning-only fallback."""
    logger = get_logger("cache.findings_cache")
    try:
        cached = get_interval_findings(
            redis_client=redis_client,
            scope=scope,
            evaluation_time=evaluation_time,
            interval_seconds=interval_seconds,
        )
    except Exception:
        logger.warning(
            "findings_cache_read_failed",
            event_type="cache.findings_cache_read_warning",
            scope=scope,
        )
        cached = None
    if cached is not None:
        return cached

    computed = compute_findings()
    try:
        set_interval_findings(
            redis_client=redis_client,
            scope=scope,
            env=scope[0],
            evaluation_time=evaluation_time,
            findings=computed,
            redis_ttl_policy=redis_ttl_policy,
            interval_seconds=interval_seconds,
        )
    except Exception:
        logger.warning(
            "findings_cache_write_failed",
            event_type="cache.findings_cache_write_warning",
            scope=scope,
        )
    return computed


def _interval_bucket_epoch_seconds(*, evaluation_time: datetime, interval_seconds: int) -> int:
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be > 0, got: {interval_seconds}")
    unix_seconds = int(evaluation_time.astimezone(UTC).timestamp())
    return unix_seconds - (unix_seconds % interval_seconds)


def _serialize_findings(findings: tuple[AnomalyFinding, ...]) -> str:
    payload = [finding.model_dump(mode="json") for finding in findings]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _deserialize_findings(payload: str) -> tuple[AnomalyFinding, ...]:
    decoded = json.loads(payload)
    if not isinstance(decoded, list):
        raise ValueError("cached findings payload must be a JSON list")
    return tuple(AnomalyFinding.model_validate(item) for item in decoded)


# ── Shard checkpoint surface (Story 4.2) ─────────────────────────────────────

# Re-export for callers that import only from this module.
build_shard_checkpoint_key = _build_shard_checkpoint_key


def set_shard_interval_checkpoint(
    *,
    redis_client: FindingsCacheClientProtocol,
    shard_id: int,
    interval_bucket: int,
    ttl_seconds: int,
) -> None:
    """Write a per-shard per-interval checkpoint marker to Redis.

    Uses a single write per shard per interval (O(1) per shard), replacing the
    previous per-scope coordination writes to satisfy NFR-SC2.
    """
    key = _build_shard_checkpoint_key(shard_id, interval_bucket)
    redis_client.set(key, "1", ex=ttl_seconds)
