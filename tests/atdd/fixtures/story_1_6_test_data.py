"""ATDD support data for Story 1.6 red-phase tests."""

from __future__ import annotations

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1


def build_gate_input(
    *,
    env: Environment = Environment.PROD,
    tier: CriticalityTier = CriticalityTier.TIER_0,
    topic_role: str = "SHARED_TOPIC",
    proposed_action: Action = Action.PAGE,
    evidence_status: EvidenceStatus = EvidenceStatus.PRESENT,
    diagnosis_confidence: float = 0.95,
    sustained: bool = True,
    peak: bool | None = True,
) -> GateInputV1:
    """Build deterministic gate input payload for Story 1.6 acceptance tests."""
    return GateInputV1(
        env=env,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role=topic_role,
        anomaly_family="VOLUME_DROP",
        criticality_tier=tier,
        proposed_action=proposed_action,
        diagnosis_confidence=diagnosis_confidence,
        sustained=sustained,
        findings=(
            Finding(
                finding_id="f-1",
                name="volume-drop",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
                is_primary=True,
                reason_codes=("VOLUME_DROP",),
            ),
        ),
        evidence_status_map={"topic_messages_in_per_sec": evidence_status},
        action_fingerprint=(
            f"{env.value}/cluster-a/stream-orders/{topic_role}/orders/VOLUME_DROP/{tier.value}"
        ),
        peak=peak,
    )
