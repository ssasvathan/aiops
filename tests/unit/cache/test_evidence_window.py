from datetime import UTC, datetime
from typing import Sequence

from aiops_triage_pipeline.cache.evidence_window import (
    build_legacy_sustained_window_cache_key,
    build_sustained_window_cache_key,
    evidence_window_ttl_seconds,
    get_sustained_window_state,
    load_sustained_window_states,
    persist_sustained_window_states,
    set_sustained_window_state,
)
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.models.peak import SustainedWindowState


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl_by_key: dict[str, int] = {}
        self.mget_calls: list[tuple[str, ...]] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        self.mget_calls.append(tuple(keys))
        return [self.store.get(key) for key in keys]

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttl_by_key[key] = ex
        return True


class _BytesRedis:
    """Simulates a Redis client that returns bytes (default without decode_responses=True)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> bytes | None:
        val = self._store.get(key)
        return val.encode("utf-8") if val is not None else None

    def mget(self, keys: Sequence[str]) -> list[bytes | None]:
        return [self.get(key) for key in keys]

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:  # noqa: ARG002
        self._store[key] = value
        return True


class _FailingReadRedis:
    def get(self, key: str) -> str | None:  # noqa: ARG002
        raise RuntimeError("redis unavailable")

    def mget(self, keys: Sequence[str]) -> list[str | None]:  # noqa: ARG002
        raise RuntimeError("redis unavailable")

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:  # noqa: ARG002
        return True


class _FailingWriteRedis(_FakeRedis):
    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:  # noqa: ARG002
        raise RuntimeError("redis unavailable")


def _ttl_policy() -> RedisTtlPolicyV1:
    base = RedisTtlsByEnv(
        evidence_window_seconds=600,
        peak_profile_seconds=3600,
        dedupe_seconds=300,
    )
    return RedisTtlPolicyV1(
        ttls_by_env={
            "local": base,
            "dev": RedisTtlsByEnv(
                evidence_window_seconds=900,
                peak_profile_seconds=7200,
                dedupe_seconds=600,
            ),
            "uat": RedisTtlsByEnv(
                evidence_window_seconds=1800,
                peak_profile_seconds=14400,
                dedupe_seconds=900,
            ),
            "prod": RedisTtlsByEnv(
                evidence_window_seconds=3600,
                peak_profile_seconds=86400,
                dedupe_seconds=1800,
            ),
        }
    )


def _identity_key() -> tuple[str, str, str, str]:
    return ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")


def _state() -> SustainedWindowState:
    return SustainedWindowState(
        identity_key=_identity_key(),
        consecutive_anomalous_buckets=3,
        last_evaluated_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )


def test_build_sustained_window_cache_key_uses_required_namespace() -> None:
    key = build_sustained_window_cache_key(_identity_key())

    assert key == "aiops:sustained:cluster-a:topic:orders:VOLUME_DROP"


def test_evidence_window_ttl_seconds_selects_env_specific_policy_value() -> None:
    ttl = evidence_window_ttl_seconds(env="dev", redis_ttl_policy=_ttl_policy())

    assert ttl == 900


def test_evidence_window_ttl_seconds_falls_back_for_unknown_env() -> None:
    ttl = evidence_window_ttl_seconds(env="stage", redis_ttl_policy=_ttl_policy())

    assert ttl == 600


def test_set_and_get_sustained_window_state_round_trip() -> None:
    redis_client = _FakeRedis()
    policy = _ttl_policy()
    state = _state()

    set_sustained_window_state(
        redis_client=redis_client,
        identity_key=state.identity_key,
        env="prod",
        state=state,
        redis_ttl_policy=policy,
    )
    loaded = get_sustained_window_state(
        redis_client=redis_client,
        identity_key=state.identity_key,
    )

    assert loaded == state
    assert redis_client.ttl_by_key["aiops:sustained:cluster-a:topic:orders:VOLUME_DROP"] == 3600


def test_set_sustained_window_state_serialization_is_deterministic() -> None:
    redis_client = _FakeRedis()
    policy = _ttl_policy()
    state = _state()

    set_sustained_window_state(
        redis_client=redis_client,
        identity_key=state.identity_key,
        env="prod",
        state=state,
        redis_ttl_policy=policy,
    )
    first_payload = redis_client.store["aiops:sustained:cluster-a:topic:orders:VOLUME_DROP"]

    set_sustained_window_state(
        redis_client=redis_client,
        identity_key=state.identity_key,
        env="prod",
        state=state,
        redis_ttl_policy=policy,
    )
    second_payload = redis_client.store["aiops:sustained:cluster-a:topic:orders:VOLUME_DROP"]

    assert first_payload == second_payload


def test_get_sustained_window_state_supports_legacy_namespace_read() -> None:
    redis_client = _FakeRedis()
    state = _state()

    legacy_key = build_legacy_sustained_window_cache_key(state.identity_key)
    redis_client.store[legacy_key] = state.model_dump_json()

    loaded = get_sustained_window_state(
        redis_client=redis_client,
        identity_key=state.identity_key,
    )

    assert loaded == state


def test_load_sustained_window_states_returns_safe_empty_on_read_failure() -> None:
    loaded = load_sustained_window_states(
        redis_client=_FailingReadRedis(),
        identity_keys=[_identity_key()],
    )

    assert loaded == {}


def test_load_sustained_window_states_uses_batched_reads_with_stable_mapping() -> None:
    redis_client = _FakeRedis()
    first_key = ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")
    second_key = ("prod", "cluster-a", "topic:payments", "VOLUME_DROP")
    first_state = SustainedWindowState(
        identity_key=first_key,
        consecutive_anomalous_buckets=2,
        last_evaluated_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )
    second_state = SustainedWindowState(
        identity_key=second_key,
        consecutive_anomalous_buckets=4,
        last_evaluated_at=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )
    redis_client.store[build_sustained_window_cache_key(first_key)] = first_state.model_dump_json()
    redis_client.store[build_sustained_window_cache_key(second_key)] = (
        second_state.model_dump_json()
    )

    loaded = load_sustained_window_states(
        redis_client=redis_client,
        identity_keys=[second_key, first_key],
    )

    assert len(redis_client.mget_calls) >= 1
    assert loaded[first_key] == first_state
    assert loaded[second_key] == second_state


def test_get_sustained_window_state_handles_bytes_response() -> None:
    """Real Redis clients return bytes by default; the get helper must handle them."""
    client = _BytesRedis()
    state = _state()

    set_sustained_window_state(
        redis_client=client,
        identity_key=state.identity_key,
        env="prod",
        state=state,
        redis_ttl_policy=_ttl_policy(),
    )
    loaded = get_sustained_window_state(
        redis_client=client,
        identity_key=state.identity_key,
    )

    assert loaded == state


def test_persist_sustained_window_states_derives_ttl_from_identity_key_env() -> None:
    redis_client = _FakeRedis()
    policy = _ttl_policy()
    # identity_key[0] = "dev" → evidence_window_seconds = 900
    dev_key: tuple[str, str, str, str] = ("dev", "cluster-a", "topic:orders", "VOLUME_DROP")
    state = SustainedWindowState(
        identity_key=dev_key,
        consecutive_anomalous_buckets=2,
        last_evaluated_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    persist_sustained_window_states(
        redis_client=redis_client,
        states_by_key={dev_key: state},
        redis_ttl_policy=policy,
    )

    assert redis_client.ttl_by_key["aiops:sustained:cluster-a:topic:orders:VOLUME_DROP"] == 900


def test_persist_sustained_window_states_ignores_write_failures() -> None:
    persist_sustained_window_states(
        redis_client=_FailingWriteRedis(),
        states_by_key={_identity_key(): _state()},
        redis_ttl_policy=_ttl_policy(),
    )
