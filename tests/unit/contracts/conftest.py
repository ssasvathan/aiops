"""Fixtures for contract unit tests."""

from datetime import datetime, timezone

import pytest

from aiops_triage_pipeline.contracts import (
    Action,
    ActionDecisionV1,
    CaseHeaderEventV1,
    CriticalityTier,
    DiagnosisConfidence,
    DiagnosisReportV1,
    Environment,
    EvidencePack,
    EvidenceStatus,
    Finding,
    GateInputV1,
    TriageExcerptV1,
)


@pytest.fixture()
def sample_finding() -> Finding:
    return Finding(
        finding_id="f1",
        name="consumer-lag",
        is_anomalous=True,
        evidence_required=("lag_metric", "throughput_metric"),
        is_primary=True,
        severity="HIGH",
        reason_codes=("LAG_THRESHOLD_EXCEEDED",),
    )


@pytest.fixture()
def sample_evidence_status_map() -> dict[str, EvidenceStatus]:
    return {
        "lag_metric": EvidenceStatus.PRESENT,
        "throughput_metric": EvidenceStatus.UNKNOWN,
    }


@pytest.fixture()
def sample_gate_input(sample_finding, sample_evidence_status_map) -> GateInputV1:
    return GateInputV1(
        env=Environment.LOCAL,
        cluster_id="cluster-1",
        stream_id="stream-1",
        topic="topic-1",
        topic_role="SOURCE_TOPIC",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.85,
        sustained=True,
        findings=(sample_finding,),
        evidence_status_map=sample_evidence_status_map,
        action_fingerprint="env/cluster-1/stream-1/SOURCE_TOPIC/topic-1/CONSUMER_LAG/TIER_0",
    )


@pytest.fixture()
def sample_action_decision() -> ActionDecisionV1:
    return ActionDecisionV1(
        final_action=Action.PAGE,
        env_cap_applied=False,
        gate_rule_ids=("AG0", "AG1", "AG2"),
        gate_reason_codes=("PASS", "PASS", "PASS"),
        action_fingerprint="env/cluster-1/stream-1/SOURCE_TOPIC/topic-1/CONSUMER_LAG/TIER_0",
        postmortem_required=True,
        postmortem_mode="SOFT",
        postmortem_reason_codes=("PM_PEAK_SUSTAINED",),
    )


@pytest.fixture()
def sample_case_header_event() -> CaseHeaderEventV1:
    return CaseHeaderEventV1(
        case_id="case-abc-123",
        env=Environment.PROD,
        cluster_id="cluster-1",
        stream_id="stream-1",
        topic="topic-1",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_0,
        final_action=Action.PAGE,
        routing_key="team-platform",
        evaluation_ts=datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture()
def sample_triage_excerpt(sample_finding, sample_evidence_status_map) -> TriageExcerptV1:
    return TriageExcerptV1(
        case_id="case-abc-123",
        env=Environment.PROD,
        cluster_id="cluster-1",
        stream_id="stream-1",
        topic="topic-1",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="team-platform",
        sustained=True,
        peak=True,
        evidence_status_map=sample_evidence_status_map,
        findings=(sample_finding,),
        triage_timestamp=datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture()
def sample_evidence_pack() -> EvidencePack:
    return EvidencePack(
        facts=("Consumer lag exceeded 10k messages for 3 consecutive windows",),
        missing_evidence=("throughput_metric",),
        matched_rules=("RULE_LAG_SUSTAINED",),
    )


@pytest.fixture()
def sample_diagnosis_report(sample_evidence_pack) -> DiagnosisReportV1:
    return DiagnosisReportV1(
        case_id="case-abc-123",
        verdict="CONSUMER_LAG_DEGRADATION",
        fault_domain="kafka-consumer",
        confidence=DiagnosisConfidence.HIGH,
        evidence_pack=sample_evidence_pack,
        next_checks=("check_consumer_offset_rate",),
        gaps=("throughput_metric unavailable",),
        triage_hash="abc123def456",
    )
