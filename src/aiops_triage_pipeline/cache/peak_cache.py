"""Redis adapter for Stage 2 peak profile caching."""

import json
from typing import Callable, Protocol

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.peak import PeakProfile, PeakScope


class PeakCacheClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by peak cache helpers."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool | None:
        ...


def build_peak_cache_key(scope: PeakScope) -> str:
    """Build deterministic cache key for one topic scope."""
    return f"peak:{scope[0]}|{scope[1]}|{scope[2]}"


def peak_profile_ttl_seconds(*, env: str, redis_ttl_policy: RedisTtlPolicyV1) -> int:
    """Read env-specific peak profile TTL from redis-ttl-policy-v1.

    Falls back to the minimum configured TTL when ``env`` has no entry, to
    avoid stale data in unexpected environments.
    """
    env_ttls = redis_ttl_policy.ttls_by_env.get(env)
    if env_ttls is None:
        fallback = min(v.peak_profile_seconds for v in redis_ttl_policy.ttls_by_env.values())
        get_logger("cache.peak_cache").warning(
            "peak_ttl_env_not_found",
            event_type="cache.peak_profile_ttl_warning",
            env=env,
            fallback_ttl_seconds=fallback,
        )
        return fallback
    return env_ttls.peak_profile_seconds


def get_peak_profile(
    *,
    redis_client: PeakCacheClientProtocol,
    scope: PeakScope,
) -> PeakProfile | None:
    """Load cached peak profile, returning None on cache miss."""
    raw = redis_client.get(build_peak_cache_key(scope))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        payload = raw.decode("utf-8")
    else:
        payload = raw
    return PeakProfile.model_validate_json(payload)


def set_peak_profile(
    *,
    redis_client: PeakCacheClientProtocol,
    scope: PeakScope,
    env: str,
    profile: PeakProfile,
    redis_ttl_policy: RedisTtlPolicyV1,
) -> None:
    """Store one peak profile under required namespace with env-specific TTL."""
    ttl = peak_profile_ttl_seconds(env=env, redis_ttl_policy=redis_ttl_policy)
    redis_client.setex(build_peak_cache_key(scope), ttl, _serialize_profile(profile))


def get_or_compute_peak_profile(
    *,
    redis_client: PeakCacheClientProtocol,
    scope: PeakScope,
    env: str,
    redis_ttl_policy: RedisTtlPolicyV1,
    compute_profile: Callable[[], PeakProfile | None],
) -> PeakProfile | None:
    """Read-through helper: use cached profile, otherwise compute and populate cache."""
    cached = get_peak_profile(redis_client=redis_client, scope=scope)
    if cached is not None:
        return cached

    computed = compute_profile()
    if computed is None:
        return None
    try:
        set_peak_profile(
            redis_client=redis_client,
            scope=scope,
            env=env,
            profile=computed,
            redis_ttl_policy=redis_ttl_policy,
        )
    except Exception:
        # Cache write failure must not prevent returning the computed profile.
        get_logger("cache.peak_cache").warning(
            "peak_cache_write_failed",
            event_type="cache.peak_cache_write_warning",
            scope=scope,
        )
    return computed


def _serialize_profile(profile: PeakProfile) -> str:
    """Serialize profile as deterministic JSON for stable cache payloads."""
    return json.dumps(profile.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
