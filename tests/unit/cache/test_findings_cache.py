import json
from datetime import UTC, datetime

from aiops_triage_pipeline.cache.findings_cache import (
    build_interval_findings_cache_key,
    build_legacy_interval_findings_cache_key,
    get_interval_findings,
    get_or_compute_interval_findings,
    interval_findings_ttl_seconds,
    set_interval_findings,
    set_shard_interval_checkpoint,
)
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.models.anomaly import AnomalyFinding


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl_by_key: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttl_by_key[key] = ex
        return True


class _BytesRedis(_FakeRedis):
    def get(self, key: str) -> bytes | None:
        value = self.store.get(key)
        return value.encode("utf-8") if value is not None else None


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


def _finding() -> AnomalyFinding:
    return AnomalyFinding(
        finding_id="VOLUME_DROP:prod|cluster-a|orders",
        anomaly_family="VOLUME_DROP",
        scope=("prod", "cluster-a", "orders"),
        severity="MEDIUM",
        reason_codes=("EXPECTED_INGRESS_BUT_LOW_TRAFFIC", "VOLUME_DROP_VS_BASELINE"),
        evidence_required=("topic_messages_in_per_sec", "total_produce_requests_per_sec"),
        is_primary=True,
    )


def test_build_interval_findings_cache_key_uses_required_namespace() -> None:
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 7, tzinfo=UTC)
    bucket = int(datetime(2026, 3, 2, 12, 5, tzinfo=UTC).timestamp())

    key = build_interval_findings_cache_key(scope=scope, evaluation_time=evaluation_time)

    assert key == f"evidence:findings|prod|cluster-a|orders|{bucket}"


def test_interval_findings_ttl_seconds_uses_evidence_window_policy_field() -> None:
    ttl = interval_findings_ttl_seconds(env="dev", redis_ttl_policy=_ttl_policy())

    assert ttl == 900


def test_set_and_get_interval_findings_round_trip() -> None:
    redis_client = _FakeRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)

    set_interval_findings(
        redis_client=redis_client,
        scope=scope,
        env="prod",
        evaluation_time=evaluation_time,
        findings=findings,
        redis_ttl_policy=_ttl_policy(),
    )
    loaded = get_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
    )

    key = build_interval_findings_cache_key(scope=scope, evaluation_time=evaluation_time)
    assert loaded == findings
    assert redis_client.ttl_by_key[key] == 3600


def test_set_interval_findings_serialization_is_deterministic() -> None:
    redis_client = _FakeRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)

    set_interval_findings(
        redis_client=redis_client,
        scope=scope,
        env="prod",
        evaluation_time=evaluation_time,
        findings=findings,
        redis_ttl_policy=_ttl_policy(),
    )
    key = build_interval_findings_cache_key(scope=scope, evaluation_time=evaluation_time)
    first_payload = redis_client.store[key]

    set_interval_findings(
        redis_client=redis_client,
        scope=scope,
        env="prod",
        evaluation_time=evaluation_time,
        findings=findings,
        redis_ttl_policy=_ttl_policy(),
    )
    second_payload = redis_client.store[key]

    assert first_payload == second_payload


def test_get_interval_findings_handles_bytes_response() -> None:
    redis_client = _BytesRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)

    set_interval_findings(
        redis_client=redis_client,
        scope=scope,
        env="prod",
        evaluation_time=evaluation_time,
        findings=findings,
        redis_ttl_policy=_ttl_policy(),
    )
    loaded = get_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
    )

    assert loaded == findings


def test_get_interval_findings_supports_legacy_namespace_read() -> None:
    redis_client = _FakeRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)

    legacy_key = build_legacy_interval_findings_cache_key(
        scope=scope,
        evaluation_time=evaluation_time,
    )
    redis_client.store[legacy_key] = json.dumps(
        [findings[0].model_dump(mode="json")],
        sort_keys=True,
        separators=(",", ":"),
    )

    loaded = get_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
    )

    assert loaded == findings


def test_get_or_compute_interval_findings_reuses_cached_value() -> None:
    redis_client = _FakeRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)
    calls = {"count": 0}

    def _compute() -> tuple[AnomalyFinding, ...]:
        calls["count"] += 1
        return findings

    first = get_or_compute_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
        redis_ttl_policy=_ttl_policy(),
        compute_findings=_compute,
    )
    second = get_or_compute_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
        redis_ttl_policy=_ttl_policy(),
        compute_findings=_compute,
    )

    assert first == findings
    assert second == findings
    assert calls["count"] == 1


def test_get_or_compute_interval_findings_ignores_read_failures() -> None:
    redis_client = _FailingReadRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)
    calls = {"count": 0}

    def _compute() -> tuple[AnomalyFinding, ...]:
        calls["count"] += 1
        return findings

    loaded = get_or_compute_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
        redis_ttl_policy=_ttl_policy(),
        compute_findings=_compute,
    )

    assert loaded == findings
    assert calls["count"] == 1


def test_get_or_compute_interval_findings_ignores_write_failures() -> None:
    redis_client = _FailingWriteRedis()
    scope = ("prod", "cluster-a", "orders")
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)
    findings = (_finding(),)

    loaded = get_or_compute_interval_findings(
        redis_client=redis_client,
        scope=scope,
        evaluation_time=evaluation_time,
        redis_ttl_policy=_ttl_policy(),
        compute_findings=lambda: findings,
    )

    assert loaded == findings


# ── Shard checkpoint surface (Story 4.2) ─────────────────────────────────────


def test_set_shard_interval_checkpoint_writes_single_key_with_ttl() -> None:
    """set_shard_interval_checkpoint writes exactly one key per shard per interval (NFR-SC2)."""

    class _RecordingClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def get(self, key: str) -> str | None:
            return None

        def set(self, key: str, value: str, *, ex: int | None = None) -> bool:
            self.calls.append({"key": key, "value": value, "ex": ex})
            return True

    client = _RecordingClient()
    set_shard_interval_checkpoint(
        redis_client=client,
        shard_id=2,
        interval_bucket=1700000600,
        ttl_seconds=660,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["key"] == "aiops:shard:checkpoint:2:1700000600"
    assert call["value"] == "1"
    assert call["ex"] == 660
