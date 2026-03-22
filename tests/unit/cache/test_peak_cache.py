from datetime import UTC, datetime
from typing import Sequence

from aiops_triage_pipeline.cache.peak_cache import (
    build_peak_cache_key,
    get_or_compute_peak_profile,
    get_peak_profile,
    load_peak_profiles,
    peak_profile_ttl_seconds,
    persist_peak_profiles,
    set_peak_profile,
)
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.models.peak import PeakProfile


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


class _FailingReadRedis(_FakeRedis):
    def get(self, key: str) -> str | None:  # noqa: ARG002
        raise RuntimeError("redis unavailable")


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


def _profile() -> PeakProfile:
    return PeakProfile(
        scope=("prod", "cluster-a", "orders"),
        source_metric="kafka_server_brokertopicmetrics_messagesinpersec",
        peak_threshold_value=120.0,
        near_peak_threshold_value=95.0,
        history_samples_count=14,
        has_sufficient_history=True,
        recompute_frequency="weekly",
        computed_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )


def test_build_peak_cache_key_uses_required_namespace() -> None:
    key = build_peak_cache_key(("prod", "cluster-a", "orders"))

    assert key == "aiops:peak:cluster-a:orders"


def test_peak_profile_ttl_seconds_selects_env_specific_policy_value() -> None:
    ttl = peak_profile_ttl_seconds(env="dev", redis_ttl_policy=_ttl_policy())

    assert ttl == 7200


def test_set_and_get_peak_profile_round_trip() -> None:
    redis_client = _FakeRedis()
    profile = _profile()
    policy = _ttl_policy()

    set_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        profile=profile,
        redis_ttl_policy=policy,
    )
    loaded = get_peak_profile(redis_client=redis_client, scope=profile.scope)

    assert loaded == profile
    assert redis_client.ttl_by_key["aiops:peak:cluster-a:orders"] == 86400


def test_get_or_compute_peak_profile_recomputes_on_miss_and_reuses_cached_value() -> None:
    redis_client = _FakeRedis()
    policy = _ttl_policy()
    profile = _profile()
    compute_calls = {"count": 0}

    def _compute() -> PeakProfile:
        compute_calls["count"] += 1
        return profile

    loaded_first = get_or_compute_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        redis_ttl_policy=policy,
        compute_profile=_compute,
    )
    loaded_second = get_or_compute_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        redis_ttl_policy=policy,
        compute_profile=_compute,
    )

    assert loaded_first == profile
    assert loaded_second == profile
    assert compute_calls["count"] == 1


def test_set_peak_profile_serialization_is_deterministic() -> None:
    redis_client = _FakeRedis()
    profile = _profile()
    policy = _ttl_policy()

    set_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        profile=profile,
        redis_ttl_policy=policy,
    )
    first_payload = redis_client.store["aiops:peak:cluster-a:orders"]

    set_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        profile=profile,
        redis_ttl_policy=policy,
    )
    second_payload = redis_client.store["aiops:peak:cluster-a:orders"]

    assert first_payload == second_payload


def test_get_or_compute_peak_profile_ignores_read_failures() -> None:
    redis_client = _FailingReadRedis()
    profile = _profile()
    policy = _ttl_policy()
    calls = {"count": 0}

    def _compute() -> PeakProfile:
        calls["count"] += 1
        return profile

    loaded = get_or_compute_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        redis_ttl_policy=policy,
        compute_profile=_compute,
    )

    assert loaded == profile
    assert calls["count"] == 1


def test_get_or_compute_peak_profile_ignores_write_failures() -> None:
    redis_client = _FailingWriteRedis()
    profile = _profile()
    policy = _ttl_policy()

    loaded = get_or_compute_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        redis_ttl_policy=policy,
        compute_profile=lambda: profile,
    )

    assert loaded == profile


def test_load_peak_profiles_uses_batched_reads_with_deterministic_mapping() -> None:
    redis_client = _FakeRedis()
    first = _profile()
    second = PeakProfile(
        scope=("prod", "cluster-a", "payments"),
        source_metric=first.source_metric,
        peak_threshold_value=88.0,
        near_peak_threshold_value=66.0,
        history_samples_count=10,
        has_sufficient_history=True,
        recompute_frequency="weekly",
        computed_at=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )
    redis_client.store[build_peak_cache_key(first.scope)] = first.model_dump_json()
    redis_client.store[build_peak_cache_key(second.scope)] = second.model_dump_json()

    loaded = load_peak_profiles(
        redis_client=redis_client,
        scopes=[second.scope, first.scope],
    )

    assert len(redis_client.mget_calls) >= 1
    assert loaded[first.scope] == first
    assert loaded[second.scope] == second


def test_persist_peak_profiles_writes_all_profiles_with_env_ttl() -> None:
    redis_client = _FakeRedis()
    profile = _profile()
    persist_peak_profiles(
        redis_client=redis_client,
        profiles_by_scope={profile.scope: profile},
        redis_ttl_policy=_ttl_policy(),
    )

    assert build_peak_cache_key(profile.scope) in redis_client.store
    assert redis_client.ttl_by_key[build_peak_cache_key(profile.scope)] == 86400
