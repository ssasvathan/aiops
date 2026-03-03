from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, EvidenceStatus
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.rulebook import (
    GateCheck,
    GateEffects,
    GateSpec,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
)
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.gating import (
    GateInputContext,
    collect_gate_inputs_by_scope,
)
from aiops_triage_pipeline.pipeline.stages.peak import collect_peak_stage_output


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


def _rulebook_policy_for_tests(required: int = 5) -> RulebookV1:
    defaults = RulebookDefaults(
        missing_series_policy="UNKNOWN_NOT_ZERO",
        required_evidence_policy="PRESENT_ONLY",
        missing_confidence_policy="DOWNGRADE",
        missing_sustained_policy="DOWNGRADE",
    )
    caps = RulebookCaps(
        max_action_by_env={"local": "OBSERVE", "dev": "OBSERVE", "stage": "NOTIFY", "prod": "PAGE"},
        max_action_by_tier_in_prod={
            "TIER_0": "PAGE",
            "TIER_1": "TICKET",
            "TIER_2": "NOTIFY",
            "UNKNOWN": "NOTIFY",
        },
        paging_denied_topic_roles=("SOURCE_TOPIC",),
    )
    gates = tuple(
        GateSpec(
            id=gate_id,
            name=f"Gate {gate_id}",
            intent="test",
            effect=GateEffects(),
            checks=(GateCheck(check_id=f"{gate_id}_CHECK", type="always_pass"),),
        )
        for gate_id in ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    )
    return RulebookV1(
        rulebook_id="rulebook.v1",
        version=1,
        evaluation_interval_minutes=5,
        sustained_intervals_required=required,
        defaults=defaults,
        caps=caps,
        gates=gates,
    )


def test_collect_gate_inputs_by_scope_propagates_unknown_evidence_status_map() -> None:
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
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=datetime(2026, 3, 3, 12, 0, tzinfo=UTC),
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )

    gate_inputs_by_scope = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: GateInputContext(
                stream_id="stream-orders",
                topic_role="SOURCE_TOPIC",
                criticality_tier=CriticalityTier.TIER_0,
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.75,
            )
        },
    )

    assert scope in gate_inputs_by_scope
    assert len(gate_inputs_by_scope[scope]) == 1
    gate_input = gate_inputs_by_scope[scope][0]
    assert gate_input.anomaly_family == "VOLUME_DROP"
    assert gate_input.evidence_status_map == dict(
        evidence_output.evidence_status_map_by_scope[scope]
    )
    assert (
        gate_input.evidence_status_map["failed_produce_requests_per_sec"]
        == EvidenceStatus.UNKNOWN
    )
    assert gate_input.topic == "orders"
    assert gate_input.consumer_group is None


def test_collect_gate_inputs_by_scope_uses_topic_context_fallback_for_group_scope() -> None:
    samples = {
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 120.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 180.0,
            },
        ],
        "consumer_group_offset": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 2.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 7.0,
            },
        ],
    }
    evidence_output = collect_evidence_stage_output(samples)
    group_scope = ("prod", "cluster-a", "payments-worker", "payments")
    topic_scope = ("prod", "cluster-a", "payments")
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=datetime(2026, 3, 3, 12, 0, tzinfo=UTC),
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )

    gate_inputs_by_scope = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            topic_scope: GateInputContext(
                stream_id="stream-payments",
                topic_role="SHARED_TOPIC",
                criticality_tier=CriticalityTier.TIER_1,
                proposed_action=Action.TICKET,
                diagnosis_confidence=0.6,
            )
        },
    )

    assert group_scope in gate_inputs_by_scope
    gate_input = gate_inputs_by_scope[group_scope][0]
    assert gate_input.consumer_group == "payments-worker"
    assert gate_input.topic == "payments"
    assert gate_input.stream_id == "stream-payments"
    assert gate_input.anomaly_family == "CONSUMER_LAG"


def test_collect_gate_inputs_by_scope_raises_when_context_missing() -> None:
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
    }
    evidence_output = collect_evidence_stage_output(samples)
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={("prod", "cluster-a", "orders"): [10.0, 20.0, 30.0, 40.0]},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=datetime(2026, 3, 3, 12, 0, tzinfo=UTC),
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )

    with pytest.raises(KeyError, match="Missing gate-input context"):
        collect_gate_inputs_by_scope(
            evidence_output=evidence_output,
            peak_output=peak_output,
            context_by_scope={},
        )
