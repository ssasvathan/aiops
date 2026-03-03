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

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool | None:
        ...


def build_sustained_window_cache_key(identity_key: SustainedIdentityKey) -> str:
    """Build deterministic cache key for one sustained identity."""
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
    """Load persisted sustained-window state, returning None on cache miss."""
    raw = redis_client.get(build_sustained_window_cache_key(identity_key))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        payload = raw.decode("utf-8")
    else:
        payload = raw
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
    for identity_key in sorted(set(identity_keys)):
        try:
            state = get_sustained_window_state(
                redis_client=redis_client,
                identity_key=identity_key,
            )
        except Exception:
            logger.warning(
                "evidence_window_cache_read_failed",
                event_type="cache.evidence_window_read_warning",
                identity_key=identity_key,
            )
            continue
        if state is not None:
            loaded[identity_key] = state
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
