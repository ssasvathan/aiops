import io
import json
from datetime import UTC, datetime, timedelta
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.pipeline.scheduler import (
    SchedulerTick,
    evaluate_scheduler_tick,
    floor_to_interval_boundary,
    next_interval_boundary,
    run_evidence_stage_cycle,
    run_gate_decision_stage_cycle,
    run_gate_input_stage_cycle,
    run_peak_stage_cycle,
)
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.gating import GateInputContext
from aiops_triage_pipeline.pipeline.stages.peak import (
    build_sustained_window_state_by_key,
    load_rulebook_policy,
)


def _peak_policy_for_tests() -> PeakPolicyV1:
    return PeakPolicyV1(
        metric="kafka_server_brokertopicmetrics_messagesinpersec",
        timezone="America/Toronto",
        recompute_frequency="weekly",
        defaults=PeakThresholdPolicy(
            peak_percentile=90,
            near_peak_percentile=95,
            bucket_minutes=15,
            min_baseline_windows=4,
        ),
    )


def _parse_logs(stream: io.StringIO) -> list[dict]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


class _FindingsRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, *, ex: int | None = None) -> bool:  # noqa: ARG002
        self.store[key] = value
        return True


class _DedupeStore:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.remembered: list[str] = []

    def is_duplicate(self, fingerprint: str) -> bool:  # noqa: ARG002
        return self.duplicate

    def remember(self, fingerprint: str) -> None:
        self.remembered.append(fingerprint)


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


def _metric_queries_for_degraded_tests() -> dict[str, MetricQueryDefinition]:
    return {
        "topic_messages_in_per_sec": MetricQueryDefinition(
            metric_key="topic_messages_in_per_sec",
            metric_name="kafka_server_brokertopicmetrics_messagesinpersec",
            role="signal",
        ),
        "consumer_group_lag": MetricQueryDefinition(
            metric_key="consumer_group_lag",
            metric_name="kafka_consumergroup_group_lag",
            role="signal",
        ),
    }


def test_floor_to_interval_boundary_aligns_to_5_minute_mark() -> None:
    now = datetime(2026, 3, 2, 12, 7, 42, tzinfo=UTC)
    assert floor_to_interval_boundary(now, interval_seconds=300) == datetime(
        2026, 3, 2, 12, 5, 0, tzinfo=UTC
    )


def test_next_interval_boundary_advances_to_next_5_minute_mark() -> None:
    now = datetime(2026, 3, 2, 12, 5, 0, tzinfo=UTC)
    assert next_interval_boundary(now, interval_seconds=300) == datetime(
        2026, 3, 2, 12, 10, 0, tzinfo=UTC
    )


def test_evaluate_scheduler_tick_tracks_drift_without_warning_under_threshold(
    log_stream: io.StringIO,
) -> None:
    tick = evaluate_scheduler_tick(
        actual_fire_time=datetime(2026, 3, 2, 12, 5, 20, tzinfo=UTC),
        previous_boundary=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        interval_seconds=300,
        drift_threshold_seconds=30,
    )

    assert tick == SchedulerTick(
        expected_boundary=datetime(2026, 3, 2, 12, 5, 0, tzinfo=UTC),
        actual_fire_time=datetime(2026, 3, 2, 12, 5, 20, tzinfo=UTC),
        drift_seconds=20,
        missed_intervals=0,
    )

    warnings = [entry for entry in _parse_logs(log_stream) if entry.get("severity") == "WARNING"]
    assert warnings == []


def test_evaluate_scheduler_tick_warns_when_drift_exceeds_threshold(
    log_stream: io.StringIO,
) -> None:
    _ = evaluate_scheduler_tick(
        actual_fire_time=datetime(2026, 3, 2, 12, 5, 35, tzinfo=UTC),
        previous_boundary=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        interval_seconds=300,
        drift_threshold_seconds=30,
    )

    warning_events = [
        entry
        for entry in _parse_logs(log_stream)
        if entry.get("event") == "scheduler_drift_threshold_exceeded"
    ]
    assert len(warning_events) == 1
    assert warning_events[0]["drift_seconds"] == 35
    assert warning_events[0]["drift_threshold_seconds"] == 30


def test_evaluate_scheduler_tick_warns_for_missed_intervals(
    log_stream: io.StringIO,
) -> None:
    _ = evaluate_scheduler_tick(
        actual_fire_time=datetime(2026, 3, 2, 12, 15, 4, tzinfo=UTC),
        previous_boundary=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        interval_seconds=300,
        drift_threshold_seconds=30,
    )

    warning_events = [
        entry
        for entry in _parse_logs(log_stream)
        if entry.get("event") == "scheduler_intervals_missed"
    ]
    assert len(warning_events) == 1
    assert warning_events[0]["missed_intervals"] == 2
    assert warning_events[0]["previous_boundary"] == "2026-03-02T12:00:00+00:00"
    assert warning_events[0]["expected_boundary"] == "2026-03-02T12:15:00+00:00"


async def test_run_evidence_stage_cycle_wires_collection_to_anomaly_output() -> None:
    class _Client:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            if metric_name == "kafka_server_brokertopicmetrics_messagesinpersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 1400.0,
                    }
                ]
            if metric_name == "kafka_server_brokertopicmetrics_totalproducerequestspersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 200.0,
                    }
                ]
            if metric_name == "kafka_server_brokertopicmetrics_failedproducerequestspersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 24.0,
                    }
                ]
            return []

    output = await run_evidence_stage_cycle(
        client=_Client(),
        metric_queries={
            "topic_messages_in_per_sec": MetricQueryDefinition(
                metric_key="topic_messages_in_per_sec",
                metric_name="kafka_server_brokertopicmetrics_messagesinpersec",
                role="signal",
            ),
            "total_produce_requests_per_sec": MetricQueryDefinition(
                metric_key="total_produce_requests_per_sec",
                metric_name="kafka_server_brokertopicmetrics_totalproducerequestspersec",
                role="signal",
            ),
            "failed_produce_requests_per_sec": MetricQueryDefinition(
                metric_key="failed_produce_requests_per_sec",
                metric_name="kafka_server_brokertopicmetrics_failedproducerequestspersec",
                role="signal",
            ),
        },
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )

    assert output.rows
    assert ("prod", "cluster-a", "orders") in output.gate_findings_by_scope


async def test_run_evidence_stage_cycle_reuses_findings_cache_on_interval_hit(
    monkeypatch,
) -> None:
    class _Client:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            if metric_name == "kafka_server_brokertopicmetrics_messagesinpersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "inventory",
                        },
                        "value": 180.0,
                    },
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "inventory",
                        },
                        "value": 0.4,
                    },
                ]
            if metric_name == "kafka_server_brokertopicmetrics_totalproducerequestspersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "inventory",
                        },
                        "value": 240.0,
                    }
                ]
            return []

    redis_client = _FindingsRedis()
    policy = _ttl_policy()
    evaluation_time = datetime(2026, 3, 2, 12, 5, tzinfo=UTC)

    first = await run_evidence_stage_cycle(
        client=_Client(),
        metric_queries={
            "topic_messages_in_per_sec": MetricQueryDefinition(
                metric_key="topic_messages_in_per_sec",
                metric_name="kafka_server_brokertopicmetrics_messagesinpersec",
                role="signal",
            ),
            "total_produce_requests_per_sec": MetricQueryDefinition(
                metric_key="total_produce_requests_per_sec",
                metric_name="kafka_server_brokertopicmetrics_totalproducerequestspersec",
                role="signal",
            ),
        },
        evaluation_time=evaluation_time,
        findings_cache_client=redis_client,
        redis_ttl_policy=policy,
    )
    assert any(key.startswith("evidence:findings|") for key in redis_client.store)

    def _raise_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("detectors should not execute on findings cache hit")

    monkeypatch.setattr(
        "aiops_triage_pipeline.pipeline.stages.anomaly._detect_consumer_lag_buildup",
        _raise_if_called,
    )
    monkeypatch.setattr(
        "aiops_triage_pipeline.pipeline.stages.anomaly._detect_throughput_constrained_proxy",
        _raise_if_called,
    )
    monkeypatch.setattr(
        "aiops_triage_pipeline.pipeline.stages.anomaly._detect_volume_drop",
        _raise_if_called,
    )

    second = await run_evidence_stage_cycle(
        client=_Client(),
        metric_queries={
            "topic_messages_in_per_sec": MetricQueryDefinition(
                metric_key="topic_messages_in_per_sec",
                metric_name="kafka_server_brokertopicmetrics_messagesinpersec",
                role="signal",
            ),
            "total_produce_requests_per_sec": MetricQueryDefinition(
                metric_key="total_produce_requests_per_sec",
                metric_name="kafka_server_brokertopicmetrics_totalproducerequestspersec",
                role="signal",
            ),
        },
        evaluation_time=evaluation_time,
        findings_cache_client=redis_client,
        redis_ttl_policy=policy,
    )

    assert second.anomaly_result == first.anomaly_result


async def test_run_evidence_stage_cycle_detects_total_outage_and_emits_pending_event() -> None:
    class _OutageClient:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            raise URLError(f"source unavailable for {metric_name}")

    registry = HealthRegistry()
    output = await run_evidence_stage_cycle(
        client=_OutageClient(),
        metric_queries=_metric_queries_for_degraded_tests(),
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
        health_registry=registry,
    )

    assert output.telemetry_degraded_active is True
    assert output.max_safe_action == Action.NOTIFY
    assert output.rows == ()
    assert output.gate_findings_by_scope == {}
    assert registry.get("prometheus") == HealthStatus.UNAVAILABLE
    assert len(output.telemetry_degraded_events) == 1
    assert output.telemetry_degraded_events[0].recovery_status == "pending"
    assert output.telemetry_degraded_events[0].affected_scope == "prometheus"


async def test_run_evidence_stage_cycle_avoids_duplicate_pending_events_while_degraded() -> None:
    class _OutageClient:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            raise URLError(f"source unavailable for {metric_name}")

    registry = HealthRegistry()
    first = await run_evidence_stage_cycle(
        client=_OutageClient(),
        metric_queries=_metric_queries_for_degraded_tests(),
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
        health_registry=registry,
    )
    second = await run_evidence_stage_cycle(
        client=_OutageClient(),
        metric_queries=_metric_queries_for_degraded_tests(),
        evaluation_time=datetime(2026, 3, 2, 12, 10, tzinfo=UTC),
        health_registry=registry,
    )

    assert len(first.telemetry_degraded_events) == 1
    assert first.telemetry_degraded_events[0].recovery_status == "pending"
    assert second.telemetry_degraded_events == ()
    assert second.telemetry_degraded_active is True
    assert registry.get("prometheus") == HealthStatus.UNAVAILABLE


async def test_run_evidence_stage_cycle_emits_resolved_event_when_prometheus_recovers() -> None:
    class _OutageClient:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            raise URLError(f"source unavailable for {metric_name}")

    class _RecoveryClient:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            if metric_name == "kafka_server_brokertopicmetrics_messagesinpersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 8.0,
                    }
                ]
            return []

    registry = HealthRegistry()
    _ = await run_evidence_stage_cycle(
        client=_OutageClient(),
        metric_queries=_metric_queries_for_degraded_tests(),
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
        health_registry=registry,
    )
    recovered = await run_evidence_stage_cycle(
        client=_RecoveryClient(),
        metric_queries=_metric_queries_for_degraded_tests(),
        evaluation_time=datetime(2026, 3, 2, 12, 10, tzinfo=UTC),
        health_registry=registry,
    )

    assert recovered.telemetry_degraded_active is False
    assert recovered.max_safe_action is None
    assert registry.get("prometheus") == HealthStatus.HEALTHY
    assert len(recovered.telemetry_degraded_events) == 1
    assert recovered.telemetry_degraded_events[0].recovery_status == "resolved"
    assert recovered.rows


def test_run_peak_stage_cycle_wires_stage1_rows_to_peak_output() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 18.0,
            }
        ],
        "total_produce_requests_per_sec": [],
    }
    evidence_output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "orders")

    peak_output = run_peak_stage_cycle(
        evidence_output=evidence_output,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
        peak_policy=_peak_policy_for_tests(),
    )

    assert scope in peak_output.classifications_by_scope
    assert scope in peak_output.peak_context_by_scope
    assert (
        evidence_output.evidence_status_map_by_scope[scope]["total_produce_requests_per_sec"]
        == EvidenceStatus.UNKNOWN
    )
    assert peak_output.evidence_status_map_by_scope == evidence_output.evidence_status_map_by_scope
    # value=18.0, history=[1..20]: near_peak_threshold=p90=18, peak_threshold=p95=19
    # 18 >= near_peak_threshold(18) and < peak_threshold(19) → NEAR_PEAK
    assert peak_output.peak_context_by_scope[scope].classification == "NEAR_PEAK"


def test_run_peak_stage_cycle_tracks_sustained_history_across_cycles() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 180.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 0.4,
            },
        ],
        "total_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 220.0,
            }
        ],
    }
    evidence_output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "inventory")
    key = ("prod", "cluster-a", "topic:inventory", "VOLUME_DROP")
    prior = {}
    rulebook_policy = load_rulebook_policy()
    peak_output = None

    for idx in range(5):
        peak_output = run_peak_stage_cycle(
            evidence_output=evidence_output,
            historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
            prior_sustained_window_state_by_key=prior,
            evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC) + timedelta(minutes=idx * 5),
            peak_policy=_peak_policy_for_tests(),
            rulebook_policy=rulebook_policy,
        )
        prior = build_sustained_window_state_by_key(dict(peak_output.sustained_by_key))

    assert peak_output is not None
    assert peak_output.sustained_by_key[key].consecutive_anomalous_buckets == 5
    assert peak_output.sustained_by_key[key].is_sustained is True


def test_run_gate_input_stage_cycle_preserves_unknown_evidence_status() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 180.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 0.4,
            },
        ],
        "total_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 220.0,
            }
        ],
        "failed_produce_requests_per_sec": [],
    }
    evidence_output = collect_evidence_stage_output(samples, max_safe_action=Action.NOTIFY)
    scope = ("prod", "cluster-a", "orders")
    peak_output = run_peak_stage_cycle(
        evidence_output=evidence_output,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
        peak_policy=_peak_policy_for_tests(),
    )
    gate_inputs_by_scope = run_gate_input_stage_cycle(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: GateInputContext(
                stream_id="stream-orders",
                topic_role="SOURCE_TOPIC",
                criticality_tier=CriticalityTier.TIER_0,
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.7,
            )
        },
    )

    assert scope in gate_inputs_by_scope
    gate_input = gate_inputs_by_scope[scope][0]
    assert gate_input.proposed_action == Action.NOTIFY
    assert (
        gate_input.evidence_status_map["failed_produce_requests_per_sec"]
        == EvidenceStatus.UNKNOWN
    )


def test_run_gate_input_stage_cycle_skips_scopes_without_topology_context() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "missing"},
                "value": 180.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "missing"},
                "value": 0.4,
            },
        ],
        "total_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "missing"},
                "value": 220.0,
            }
        ],
    }
    evidence_output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "missing")
    peak_output = run_peak_stage_cycle(
        evidence_output=evidence_output,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        evaluation_time=datetime(2026, 3, 4, 12, 5, tzinfo=UTC),
        peak_policy=_peak_policy_for_tests(),
    )

    gate_inputs_by_scope = run_gate_input_stage_cycle(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={},
    )

    assert gate_inputs_by_scope == {}


def test_run_gate_decision_stage_cycle_returns_decisions_by_scope() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.92,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert scope in decisions_by_scope
    assert len(decisions_by_scope[scope]) == 1
    assert decisions_by_scope[scope][0].final_action == Action.PAGE
    assert decisions_by_scope[scope][0].gate_rule_ids == (
        "AG0",
        "AG1",
        "AG2",
        "AG3",
        "AG4",
        "AG5",
        "AG6",
    )


def test_run_gate_decision_stage_cycle_applies_ag2_insufficient_evidence_downgrade() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.92,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "UNKNOWN"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.NOTIFY
    assert "AG2_INSUFFICIENT_EVIDENCE" in decision.gate_reason_codes
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_applies_ag3_source_topic_page_denial() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SOURCE_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.92,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SOURCE_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.TICKET
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" in decision.gate_reason_codes
    assert "AG2_INSUFFICIENT_EVIDENCE" not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_applies_ag4_not_sustained_downgrade() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.92,
                sustained=False,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.OBSERVE
    assert "NOT_SUSTAINED" in decision.gate_reason_codes
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_applies_ag4_low_confidence_downgrade() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.59,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.OBSERVE
    assert "LOW_CONFIDENCE" in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_ag4_boundary_confidence_keeps_high_urgency() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.6,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.PAGE
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


@pytest.mark.parametrize(
    ("confidence", "sustained", "expected_action", "expected_reason_codes"),
    [
        (0.92, False, Action.OBSERVE, ("NOT_SUSTAINED",)),
        (0.59, True, Action.OBSERVE, ("LOW_CONFIDENCE",)),
        (0.6, True, Action.TICKET, ()),
    ],
)
def test_run_gate_decision_stage_cycle_applies_ag4_to_ticket_actions(
    confidence: float,
    sustained: bool,
    expected_action: Action,
    expected_reason_codes: tuple[str, ...],
) -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="TICKET",
                diagnosis_confidence=confidence,
                sustained=sustained,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == expected_action
    for reason_code in expected_reason_codes:
        assert reason_code in decision.gate_reason_codes
    for reason_code in {"LOW_CONFIDENCE", "NOT_SUSTAINED"} - set(expected_reason_codes):
        assert reason_code not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_ag2_reduction_prevents_ag4_reason_codes() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.59,
                sustained=False,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "UNKNOWN"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.NOTIFY
    assert "AG2_INSUFFICIENT_EVIDENCE" in decision.gate_reason_codes
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_ag4_enforces_thresholds_after_ag3_reduction() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SOURCE_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.59,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SOURCE_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.OBSERVE
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" in decision.gate_reason_codes
    assert "LOW_CONFIDENCE" in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


def test_run_gate_decision_stage_cycle_ag4_both_failures_preserve_reason_code_order() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.59,
                sustained=False,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.OBSERVE
    assert tuple(
        code for code in decision.gate_reason_codes if code in {"LOW_CONFIDENCE", "NOT_SUSTAINED"}
    ) == ("LOW_CONFIDENCE", "NOT_SUSTAINED")


def test_run_gate_decision_stage_cycle_ag4_downgrade_keeps_downstream_semantics() -> None:
    scope = ("prod", "cluster-a", "orders")
    dedupe_store = _DedupeStore(duplicate=True)
    gate_inputs_by_scope = {
        scope: (
            GateInputV1(
                env="prod",
                cluster_id="cluster-a",
                stream_id="stream-orders",
                topic="orders",
                topic_role="SHARED_TOPIC",
                anomaly_family="VOLUME_DROP",
                criticality_tier="TIER_0",
                proposed_action="PAGE",
                diagnosis_confidence=0.59,
                sustained=True,
                findings=(
                    Finding(
                        finding_id="f-1",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                    ),
                ),
                evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
                peak=True,
            ),
        )
    }

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    decision = decisions_by_scope[scope][0]
    assert decision.final_action == Action.OBSERVE
    assert "LOW_CONFIDENCE" in decision.gate_reason_codes
    assert "AG5_DUPLICATE_SUPPRESSED" not in decision.gate_reason_codes
    assert dedupe_store.remembered == []
    assert decision.postmortem_required is True
    assert decision.postmortem_reason_codes == ("PM_PEAK_SUSTAINED",)


def test_run_gate_decision_stage_cycle_surfaces_ag1_caps_by_scope() -> None:
    dev_scope = ("dev", "cluster-a", "orders")
    prod_scope = ("prod", "cluster-a", "payments")
    dedupe_store = _DedupeStore(duplicate=False)

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={
            dev_scope: (
                GateInputV1(
                    env="dev",
                    cluster_id="cluster-a",
                    stream_id="stream-orders",
                    topic="orders",
                    topic_role="SHARED_TOPIC",
                    anomaly_family="VOLUME_DROP",
                    criticality_tier="TIER_0",
                    proposed_action="PAGE",
                    diagnosis_confidence=0.92,
                    sustained=True,
                    findings=(
                        Finding(
                            finding_id="dev-finding",
                            name="volume-drop",
                            is_anomalous=True,
                            evidence_required=("topic_messages_in_per_sec",),
                            is_primary=True,
                        ),
                    ),
                    evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                    action_fingerprint=(
                        "dev/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0"
                    ),
                    peak=True,
                ),
            ),
            prod_scope: (
                GateInputV1(
                    env="prod",
                    cluster_id="cluster-a",
                    stream_id="stream-payments",
                    topic="payments",
                    topic_role="SHARED_TOPIC",
                    anomaly_family="VOLUME_DROP",
                    criticality_tier="TIER_1",
                    proposed_action="PAGE",
                    diagnosis_confidence=0.92,
                    sustained=True,
                    findings=(
                        Finding(
                            finding_id="prod-finding",
                            name="volume-drop",
                            is_anomalous=True,
                            evidence_required=("topic_messages_in_per_sec",),
                            is_primary=True,
                        ),
                    ),
                    evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
                    action_fingerprint=(
                        "prod/cluster-a/stream-payments/SHARED_TOPIC/payments/VOLUME_DROP/TIER_1"
                    ),
                    peak=True,
                ),
            ),
        },
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    dev_decision = decisions_by_scope[dev_scope][0]
    assert dev_decision.final_action == Action.NOTIFY
    assert dev_decision.env_cap_applied is True
    assert "AG1_ENV_OR_TIER_CAP" in dev_decision.gate_reason_codes
    assert dev_decision.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")

    prod_decision = decisions_by_scope[prod_scope][0]
    assert prod_decision.final_action == Action.TICKET
    assert prod_decision.env_cap_applied is False
    assert "AG1_ENV_OR_TIER_CAP" in prod_decision.gate_reason_codes
    assert prod_decision.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")


def test_run_gate_decision_stage_cycle_wires_dedupe_store() -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_input = GateInputV1(
        env="prod",
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role="SHARED_TOPIC",
        anomaly_family="VOLUME_DROP",
        criticality_tier="TIER_0",
        proposed_action="PAGE",
        diagnosis_confidence=0.92,
        sustained=True,
        findings=(
            Finding(
                finding_id="f-1",
                name="volume-drop",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
                is_primary=True,
            ),
        ),
        evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
        action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
        peak=True,
    )
    dedupe_store = _DedupeStore(duplicate=True)

    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={scope: (gate_input,)},
        rulebook_policy=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert decisions_by_scope[scope][0].final_action == Action.OBSERVE
    assert decisions_by_scope[scope][0].gate_reason_codes == ("AG5_DUPLICATE_SUPPRESSED",)
    assert dedupe_store.remembered == []


def test_run_gate_decision_stage_cycle_requires_explicit_rulebook_policy() -> None:
    with pytest.raises(ValueError, match="rulebook_policy is required"):
        run_gate_decision_stage_cycle(gate_inputs_by_scope={})
