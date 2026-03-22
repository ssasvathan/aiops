from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.rule_engine.predicates import (
    has_required_fields_present,
    has_sufficient_required_evidence,
)


def _gate_input() -> GateInputV1:
    return GateInputV1(
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role="SHARED_TOPIC",
        anomaly_family="VOLUME_DROP",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.95,
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
        evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.PRESENT},
        action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
    )


def test_has_required_fields_present_validates_findings_and_fingerprint() -> None:
    assert has_required_fields_present(_gate_input()) is True
    assert has_required_fields_present(_gate_input().model_copy(update={"findings": ()})) is False
    assert (
        has_required_fields_present(
            _gate_input().model_copy(update={"action_fingerprint": "   "})
        )
        is False
    )


def test_has_sufficient_required_evidence_preserves_unknown_semantics() -> None:
    gate_input = _gate_input().model_copy(
        update={"evidence_status_map": {"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN}}
    )
    assert has_sufficient_required_evidence(gate_input) is False


def test_has_sufficient_required_evidence_allows_explicit_non_present_exceptions() -> None:
    gate_input = _gate_input().model_copy(
        update={
            "findings": (
                Finding(
                    finding_id="f-allow-unknown",
                    name="volume-drop",
                    is_anomalous=True,
                    evidence_required=("topic_messages_in_per_sec",),
                    is_primary=True,
                    allowed_non_present_statuses_by_evidence={
                        "topic_messages_in_per_sec": (EvidenceStatus.UNKNOWN,)
                    },
                ),
            ),
            "evidence_status_map": {"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN},
        }
    )

    assert has_sufficient_required_evidence(gate_input) is True
