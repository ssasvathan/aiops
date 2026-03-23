"""ATDD fixture builders for Story 3.3 LLM invocation + prompt enrichment."""

from __future__ import annotations

from datetime import UTC, datetime

from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1


def build_case_header_event(case_id: str = "case-3-3-red-001") -> CaseHeaderEventV1:
    """Build a cold-path header event intentionally outside old eligibility gates."""
    return CaseHeaderEventV1(
        case_id=case_id,
        env=Environment.LOCAL,
        cluster_id="cluster-story-3-3",
        stream_id="stream-story-3-3",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_1,
        final_action=Action.NOTIFY,
        routing_key="OWN::Streaming::Payments",
        evaluation_ts=datetime(2026, 3, 22, 22, 0, tzinfo=UTC),
    )


def build_triage_excerpt(case_id: str = "case-3-3-red-001") -> TriageExcerptV1:
    """Build excerpt that represents non-prod/non-tier0/non-sustained all-case invocation."""
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.LOCAL,
        cluster_id="cluster-story-3-3",
        stream_id="stream-story-3-3",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_1,
        routing_key="OWN::Streaming::Payments",
        sustained=False,
        peak=False,
        evidence_status_map={
            "consumer_lag": EvidenceStatus.UNKNOWN,
            "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
        },
        findings=(
            Finding(
                finding_id="F-3-3-001",
                name="lag_growth_on_shared_topic",
                is_anomalous=True,
                severity="HIGH",
                reason_codes=("LAG_INCREASING", "BACKLOG_PERSISTENT"),
                evidence_required=("consumer_lag", "topic_messages_in_per_sec"),
                is_primary=True,
            ),
        ),
        triage_timestamp=datetime(2026, 3, 22, 22, 0, tzinfo=UTC),
    )
