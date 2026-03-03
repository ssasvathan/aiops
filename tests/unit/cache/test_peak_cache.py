from datetime import UTC, datetime

from aiops_triage_pipeline.cache.peak_cache import (
    build_peak_cache_key,
    get_or_compute_peak_profile,
    get_peak_profile,
    peak_profile_ttl_seconds,
    set_peak_profile,
)
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.models.peak import PeakProfile


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl_by_key: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self.store[key] = value
        self.ttl_by_key[key] = ttl_seconds
        return True


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

    assert key == "peak:prod|cluster-a|orders"


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
    assert redis_client.ttl_by_key["peak:prod|cluster-a|orders"] == 86400


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
    first_payload = redis_client.store["peak:prod|cluster-a|orders"]

    set_peak_profile(
        redis_client=redis_client,
        scope=profile.scope,
        env="prod",
        profile=profile,
        redis_ttl_policy=policy,
    )
    second_payload = redis_client.store["peak:prod|cluster-a|orders"]

    assert first_payload == second_payload
