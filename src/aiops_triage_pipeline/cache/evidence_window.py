"""Redis adapter for sustained evidence-window streak state."""

import json
from collections.abc import Sequence
from typing import Protocol

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.peak import SustainedIdentityKey, SustainedWindowState


class EvidenceWindowCacheClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by evidence-window helpers."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]:
        ...

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool | None:
        ...


def build_sustained_window_cache_key(identity_key: SustainedIdentityKey) -> str:
    """Build deterministic cache key for one sustained identity."""
    # D1 namespace alignment: aiops:{type}:{scope_key}
    # env is omitted by design because Redis is deployed per environment.
    return f"aiops:sustained:{identity_key[1]}:{identity_key[2]}:{identity_key[3]}"


def build_previous_sustained_window_cache_key(identity_key: SustainedIdentityKey) -> str:
    """Build previous-generation key used before D1 namespace alignment."""
    return f"evidence:{identity_key[0]}|{identity_key[1]}|{identity_key[2]}|{identity_key[3]}"


def build_legacy_sustained_window_cache_key(identity_key: SustainedIdentityKey) -> str:
    """Build legacy cache key using the pre-namespace-alignment format."""
    return (
        f"evidence_window:{identity_key[0]}|{identity_key[1]}|"
        f"{identity_key[2]}|{identity_key[3]}"
    )


def evidence_window_ttl_seconds(*, env: str, redis_ttl_policy: RedisTtlPolicyV1) -> int:
    """Read env-specific evidence-window TTL from redis-ttl-policy-v1."""
    env_ttls = redis_ttl_policy.ttls_by_env.get(env)
    if env_ttls is None:
        fallback = min(v.evidence_window_seconds for v in redis_ttl_policy.ttls_by_env.values())
        get_logger("cache.evidence_window").warning(
            "evidence_window_ttl_env_not_found",
            event_type="cache.evidence_window_ttl_warning",
            env=env,
            fallback_ttl_seconds=fallback,
        )
        return fallback
    return env_ttls.evidence_window_seconds


def get_sustained_window_state(
    *,
    redis_client: EvidenceWindowCacheClientProtocol,
    identity_key: SustainedIdentityKey,
) -> SustainedWindowState | None:
    """Load persisted sustained-window state, returning None on cache miss.

    Reads the architecture-required key first, then falls back to the legacy
    namespace to support in-place rollout without immediate cache invalidation.
    """
    raw = redis_client.get(build_sustained_window_cache_key(identity_key))
    if raw is None:
        raw = redis_client.get(build_previous_sustained_window_cache_key(identity_key))
    if raw is None:
        raw = redis_client.get(build_legacy_sustained_window_cache_key(identity_key))
    if raw is None:
        return None
    payload = _decode_payload(raw)
    return SustainedWindowState.model_validate_json(payload)


def set_sustained_window_state(
    *,
    redis_client: EvidenceWindowCacheClientProtocol,
    identity_key: SustainedIdentityKey,
    env: str,
    state: SustainedWindowState,
    redis_ttl_policy: RedisTtlPolicyV1,
) -> None:
    """Store sustained-window streak state with env-specific TTL."""
    ttl = evidence_window_ttl_seconds(env=env, redis_ttl_policy=redis_ttl_policy)
    redis_client.set(
        build_sustained_window_cache_key(identity_key),
        _serialize_state(state),
        ex=ttl,
    )


def load_sustained_window_states(
    *,
    redis_client: EvidenceWindowCacheClientProtocol,
    identity_keys: Sequence[SustainedIdentityKey],
) -> dict[SustainedIdentityKey, SustainedWindowState]:
    """Best-effort bulk load of sustained-window state.

    Any read error is downgraded to warning and omitted, so hot path computation can continue.
    """
    logger = get_logger("cache.evidence_window")
    loaded: dict[SustainedIdentityKey, SustainedWindowState] = {}
    unique_keys = sorted(set(identity_keys))
    if not unique_keys:
        return loaded

    try:
        primary_values = _bulk_get_values(
            redis_client=redis_client,
            keys=[build_sustained_window_cache_key(identity_key) for identity_key in unique_keys],
        )
    except Exception:
        logger.warning(
            "evidence_window_cache_read_failed",
            event_type="cache.evidence_window_read_warning",
            identity_key="*",
        )
        return loaded

    missing_identity_keys: list[SustainedIdentityKey] = []
    for identity_key, raw in zip(unique_keys, primary_values, strict=True):
        if raw is None:
            missing_identity_keys.append(identity_key)
            continue
        try:
            loaded[identity_key] = SustainedWindowState.model_validate_json(_decode_payload(raw))
        except Exception:
            logger.warning(
                "evidence_window_cache_payload_invalid",
                event_type="cache.evidence_window_read_warning",
                identity_key=identity_key,
            )

    if not missing_identity_keys:
        return loaded

    try:
        previous_values = _bulk_get_values(
            redis_client=redis_client,
            keys=[
                build_previous_sustained_window_cache_key(identity_key)
                for identity_key in missing_identity_keys
            ],
        )
    except Exception:
        logger.warning(
            "evidence_window_cache_read_failed",
            event_type="cache.evidence_window_read_warning",
            identity_key="*",
        )
        return loaded

    legacy_fallback_keys: list[SustainedIdentityKey] = []
    for identity_key, raw in zip(missing_identity_keys, previous_values, strict=True):
        if raw is None:
            legacy_fallback_keys.append(identity_key)
            continue
        try:
            loaded[identity_key] = SustainedWindowState.model_validate_json(_decode_payload(raw))
        except Exception:
            logger.warning(
                "evidence_window_cache_payload_invalid",
                event_type="cache.evidence_window_read_warning",
                identity_key=identity_key,
            )

    if not legacy_fallback_keys:
        return loaded

    try:
        legacy_values = _bulk_get_values(
            redis_client=redis_client,
            keys=[
                build_legacy_sustained_window_cache_key(identity_key)
                for identity_key in legacy_fallback_keys
            ],
        )
    except Exception:
        logger.warning(
            "evidence_window_cache_read_failed",
            event_type="cache.evidence_window_read_warning",
            identity_key="*",
        )
        return loaded

    for identity_key, raw in zip(legacy_fallback_keys, legacy_values, strict=True):
        if raw is None:
            continue
        try:
            loaded[identity_key] = SustainedWindowState.model_validate_json(_decode_payload(raw))
        except Exception:
            logger.warning(
                "evidence_window_cache_payload_invalid",
                event_type="cache.evidence_window_read_warning",
                identity_key=identity_key,
            )
    return loaded


def persist_sustained_window_states(
    *,
    redis_client: EvidenceWindowCacheClientProtocol,
    states_by_key: dict[SustainedIdentityKey, SustainedWindowState],
    redis_ttl_policy: RedisTtlPolicyV1,
) -> None:
    """Best-effort bulk persist of sustained-window state.

    TTL is derived from the env encoded in each identity key (index 0) so that
    keys from different environments receive the correct policy TTL.
    Write failures are logged and ignored so streak persistence never crashes the hot path.
    """
    logger = get_logger("cache.evidence_window")
    for identity_key, state in sorted(states_by_key.items()):
        try:
            set_sustained_window_state(
                redis_client=redis_client,
                identity_key=identity_key,
                env=identity_key[0],
                state=state,
                redis_ttl_policy=redis_ttl_policy,
            )
        except Exception:
            logger.warning(
                "evidence_window_cache_write_failed",
                event_type="cache.evidence_window_write_warning",
                identity_key=identity_key,
            )


def _serialize_state(state: SustainedWindowState) -> str:
    """Serialize sustained-window state as deterministic JSON."""
    return json.dumps(state.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _decode_payload(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw


def _bulk_get_values(
    *,
    redis_client: EvidenceWindowCacheClientProtocol,
    keys: Sequence[str],
) -> Sequence[str | bytes | None]:
    mget = getattr(redis_client, "mget", None)
    if callable(mget):
        return list(mget(keys))
    return [redis_client.get(key) for key in keys]
