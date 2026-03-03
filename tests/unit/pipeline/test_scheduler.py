import io
import json
from datetime import UTC, datetime, timedelta

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, EvidenceStatus
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.pipeline.scheduler import (
    SchedulerTick,
    evaluate_scheduler_tick,
    floor_to_interval_boundary,
    next_interval_boundary,
    run_evidence_stage_cycle,
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
    evidence_output = collect_evidence_stage_output(samples)
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
    assert (
        gate_input.evidence_status_map["failed_produce_requests_per_sec"]
        == EvidenceStatus.UNKNOWN
    )
