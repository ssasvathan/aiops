from datetime import UTC, datetime
from typing import Sequence

from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.pipeline.baseline_store import (
    build_baseline_cache_key,
    load_metric_baselines,
    persist_metric_baselines,
)


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


class _FailingRedis:
    def get(self, key: str) -> str | None:  # noqa: ARG002
        raise RuntimeError("redis unavailable")

    def mget(self, keys: Sequence[str]) -> list[str | None]:  # noqa: ARG002
        raise RuntimeError("redis unavailable")

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


def test_build_baseline_cache_key_uses_d1_namespace() -> None:
    key = build_baseline_cache_key(
        source="prometheus",
        scope=("prod", "cluster-a", "orders"),
        metric_key="topic_messages_in_per_sec",
    )

    assert key == "aiops:baseline:prometheus:prod|cluster-a|orders:topic_messages_in_per_sec"


def test_load_metric_baselines_uses_batch_reads() -> None:
    redis_client = _FakeRedis()
    key = build_baseline_cache_key(
        source="prometheus",
        scope=("prod", "cluster-a", "orders"),
        metric_key="topic_messages_in_per_sec",
    )
    redis_client.store[key] = (
        '{"baseline_value":180.5,"computed_at":"2026-03-02T12:00:00+00:00","source":"prometheus"}'
    )

    loaded = load_metric_baselines(
        redis_client=redis_client,
        source="prometheus",
        scope_metric_pairs=[(("prod", "cluster-a", "orders"), "topic_messages_in_per_sec")],
    )

    assert len(redis_client.mget_calls) == 1
    assert loaded[("prod", "cluster-a", "orders")]["topic_messages_in_per_sec"] == 180.5


def test_persist_metric_baselines_uses_env_specific_ttl_policy() -> None:
    redis_client = _FakeRedis()
    persist_metric_baselines(
        redis_client=redis_client,
        source="prometheus",
        baselines_by_scope_metric={
            ("dev", "cluster-a", "orders"): {
                "topic_messages_in_per_sec": 120.0,
            }
        },
        redis_ttl_policy=_ttl_policy(),
        computed_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    key = build_baseline_cache_key(
        source="prometheus",
        scope=("dev", "cluster-a", "orders"),
        metric_key="topic_messages_in_per_sec",
    )
    assert key in redis_client.store
    assert redis_client.ttl_by_key[key] == 7200


def test_baseline_store_degrades_on_redis_errors() -> None:
    loaded = load_metric_baselines(
        redis_client=_FailingRedis(),
        source="prometheus",
        scope_metric_pairs=[(("prod", "cluster-a", "orders"), "topic_messages_in_per_sec")],
    )

    assert loaded == {}
    persist_metric_baselines(
        redis_client=_FailingRedis(),
        source="prometheus",
        baselines_by_scope_metric={
            ("prod", "cluster-a", "orders"): {"topic_messages_in_per_sec": 150.0}
        },
        redis_ttl_policy=_ttl_policy(),
    )
