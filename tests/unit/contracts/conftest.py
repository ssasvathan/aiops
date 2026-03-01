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
    GateEffects,
    GateInputV1,
    GateSpec,
    LocalDevContractV1,
    LocalDevIntegrationModes,
    MetricDefinition,
    MetricIdentityConfig,
    OutboxPolicyV1,
    OutboxRetentionPolicy,
    PeakPolicyV1,
    PeakThresholdPolicy,
    PrometheusMetricsContractV1,
    RedisTtlPolicyV1,
    RedisTtlsByEnv,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
    ServiceNowLinkageContractV1,
    TopologyRegistryLoaderRulesV1,
    TriageExcerptV1,
    TruthfulnessConfig,
)

# ── Event Contract Fixtures (Story 1.2) ──────────────────────────────────────


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


# ── Policy Contract Fixtures (Story 1.3) ──────────────────────────────────────


def _gate(gate_id: str) -> GateSpec:
    """Build a minimal GateSpec for use in test fixtures."""
    return GateSpec(id=gate_id, name=gate_id, intent="Required gate.", effect=GateEffects())


@pytest.fixture()
def minimal_rulebook() -> RulebookV1:
    return RulebookV1(
        rulebook_id="rulebook.v1",
        version=1,
        evaluation_interval_minutes=5,
        sustained_intervals_required=5,
        defaults=RulebookDefaults(
            missing_series_policy="UNKNOWN_NOT_ZERO",
            required_evidence_policy="PRESENT_ONLY",
            missing_confidence_policy="DOWNGRADE",
            missing_sustained_policy="DOWNGRADE",
        ),
        caps=RulebookCaps(
            max_action_by_env={"local": "OBSERVE", "dev": "OBSERVE", "prod": "PAGE"},
            max_action_by_tier_in_prod={"TIER_0": "PAGE", "TIER_1": "TICKET", "TIER_2": "NOTIFY"},
            paging_denied_topic_roles=("SOURCE_TOPIC",),
        ),
        gates=(
            _gate("AG0"), _gate("AG1"), _gate("AG2"), _gate("AG3"),
            _gate("AG4"), _gate("AG5"), _gate("AG6"),
        ),
    )


@pytest.fixture()
def minimal_peak_policy() -> PeakPolicyV1:
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


@pytest.fixture()
def minimal_prometheus_metrics() -> PrometheusMetricsContractV1:
    return PrometheusMetricsContractV1(
        version="v1",
        date="2026-02-22",
        status="FROZEN",
        identity=MetricIdentityConfig(
            cluster_id_rule="cluster_id := cluster_name (exact string; no transforms)",
            topic_identity_labels=("env", "cluster_name", "topic"),
            lag_identity_labels=("env", "cluster_name", "group", "topic"),
            ignore_labels_for_identity=("instance", "job", "nodes_group"),
        ),
        metrics={
            "consumer_group_lag": MetricDefinition(
                canonical="kafka_consumergroup_group_lag",
                role="Primary lag signal",
            ),
        },
        truthfulness=TruthfulnessConfig(
            missing_series={"rule": "Missing series must map to EvidenceStatus=UNKNOWN."},
            partition={"rule": "partition is aggregation-only; never identity."},
        ),
        notes=("Example note.",),
    )


@pytest.fixture()
def minimal_redis_ttl() -> RedisTtlPolicyV1:
    base = RedisTtlsByEnv(
        evidence_window_seconds=600, peak_profile_seconds=3600, dedupe_seconds=300
    )
    return RedisTtlPolicyV1(
        ttls_by_env={
            "local": base,
            "dev": base,
            "uat": base,
            "prod": RedisTtlsByEnv(
                evidence_window_seconds=3600,
                peak_profile_seconds=86400,
                dedupe_seconds=1800,
            ),
        }
    )


@pytest.fixture()
def minimal_outbox_policy() -> OutboxPolicyV1:
    base = OutboxRetentionPolicy(sent_retention_days=1, dead_retention_days=7)
    return OutboxPolicyV1(
        retention_by_env={
            "local": base,
            "dev": base,
            "uat": base,
            "prod": OutboxRetentionPolicy(sent_retention_days=14, dead_retention_days=90),
        }
    )


@pytest.fixture()
def minimal_sn_linkage() -> ServiceNowLinkageContractV1:
    return ServiceNowLinkageContractV1()


@pytest.fixture()
def minimal_local_dev() -> LocalDevContractV1:
    return LocalDevContractV1(
        integration_modes=LocalDevIntegrationModes(),
    )


@pytest.fixture()
def minimal_topology_registry() -> TopologyRegistryLoaderRulesV1:
    return TopologyRegistryLoaderRulesV1()
