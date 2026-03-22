"""Redis adapter for Stage 2 peak profile caching."""

import json
from collections.abc import Mapping, Sequence
from typing import Callable, Protocol

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.peak import PeakProfile, PeakScope


class PeakCacheClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by peak cache helpers."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]:
        ...

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool | None:
        ...


def build_peak_cache_key(scope: PeakScope) -> str:
    """Build deterministic cache key for one topic scope."""
    return f"aiops:peak:{scope[1]}:{scope[2]}"


def build_legacy_peak_cache_key(scope: PeakScope) -> str:
    """Build legacy cache key using the pre-namespace-alignment format."""
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
    """Load cached peak profile, returning None on cache miss.

    Reads the architecture-required key first, then falls back to the legacy
    namespace to support in-place rollout without immediate cache invalidation.
    """
    raw = redis_client.get(build_peak_cache_key(scope))
    if raw is None:
        raw = redis_client.get(build_legacy_peak_cache_key(scope))
    if raw is None:
        return None
    payload = _decode_payload(raw)
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
    redis_client.set(build_peak_cache_key(scope), _serialize_profile(profile), ex=ttl)


def get_or_compute_peak_profile(
    *,
    redis_client: PeakCacheClientProtocol,
    scope: PeakScope,
    env: str,
    redis_ttl_policy: RedisTtlPolicyV1,
    compute_profile: Callable[[], PeakProfile | None],
) -> PeakProfile | None:
    """Read-through helper: use cached profile, otherwise compute and populate cache."""
    try:
        cached = get_peak_profile(redis_client=redis_client, scope=scope)
    except Exception:
        get_logger("cache.peak_cache").warning(
            "peak_cache_read_failed",
            event_type="cache.peak_cache_read_warning",
            scope=scope,
        )
        cached = None
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


def load_peak_profiles(
    *,
    redis_client: PeakCacheClientProtocol,
    scopes: Sequence[PeakScope],
) -> dict[PeakScope, PeakProfile]:
    """Best-effort bulk load of peak profiles keyed by normalized scope."""
    logger = get_logger("cache.peak_cache")
    loaded: dict[PeakScope, PeakProfile] = {}
    unique_scopes = sorted(set(scopes))
    if not unique_scopes:
        return loaded

    try:
        primary_values = _bulk_get_values(
            redis_client=redis_client,
            keys=[build_peak_cache_key(scope) for scope in unique_scopes],
        )
    except Exception:
        logger.warning(
            "peak_cache_bulk_read_failed",
            event_type="cache.peak_cache_bulk_read_warning",
            scope_count=len(unique_scopes),
        )
        return loaded

    missing_scopes: list[PeakScope] = []
    for scope, raw in zip(unique_scopes, primary_values, strict=True):
        if raw is None:
            missing_scopes.append(scope)
            continue
        try:
            loaded[scope] = PeakProfile.model_validate_json(_decode_payload(raw))
        except Exception:
            logger.warning(
                "peak_cache_payload_invalid",
                event_type="cache.peak_cache_payload_warning",
                scope=scope,
            )

    if not missing_scopes:
        return loaded

    try:
        legacy_values = _bulk_get_values(
            redis_client=redis_client,
            keys=[build_legacy_peak_cache_key(scope) for scope in missing_scopes],
        )
    except Exception:
        logger.warning(
            "peak_cache_legacy_bulk_read_failed",
            event_type="cache.peak_cache_bulk_read_warning",
            scope_count=len(missing_scopes),
        )
        return loaded

    for scope, raw in zip(missing_scopes, legacy_values, strict=True):
        if raw is None:
            continue
        try:
            loaded[scope] = PeakProfile.model_validate_json(_decode_payload(raw))
        except Exception:
            logger.warning(
                "peak_cache_payload_invalid",
                event_type="cache.peak_cache_payload_warning",
                scope=scope,
            )
    return loaded


def persist_peak_profiles(
    *,
    redis_client: PeakCacheClientProtocol,
    profiles_by_scope: Mapping[PeakScope, PeakProfile],
    redis_ttl_policy: RedisTtlPolicyV1,
) -> None:
    """Best-effort bulk persist of peak profiles with env-specific TTL."""
    logger = get_logger("cache.peak_cache")
    for scope, profile in sorted(profiles_by_scope.items()):
        try:
            set_peak_profile(
                redis_client=redis_client,
                scope=scope,
                env=scope[0],
                profile=profile,
                redis_ttl_policy=redis_ttl_policy,
            )
        except Exception:
            logger.warning(
                "peak_cache_write_failed",
                event_type="cache.peak_cache_write_warning",
                scope=scope,
            )


def _serialize_profile(profile: PeakProfile) -> str:
    """Serialize profile as deterministic JSON for stable cache payloads."""
    return json.dumps(profile.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _decode_payload(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw


def _bulk_get_values(
    *,
    redis_client: PeakCacheClientProtocol,
    keys: Sequence[str],
) -> Sequence[str | bytes | None]:
    mget = getattr(redis_client, "mget", None)
    if callable(mget):
        return list(mget(keys))
    return [redis_client.get(key) for key in keys]
