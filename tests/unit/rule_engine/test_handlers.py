from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy
from aiops_triage_pipeline.rule_engine.handlers import HANDLER_REGISTRY


def _gate_input() -> GateInputV1:
    return GateInputV1(
        env=Environment.UAT,
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
        action_fingerprint="uat/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
    )


def test_handler_registry_is_frozen_and_deterministic() -> None:
    assert tuple(HANDLER_REGISTRY) == (
        "required_fields_present",
        "cap_by_env",
        "cap_by_tier_in_prod",
        "required_evidence_present",
        "always_fail",
        "always_pass",
    )


def test_cap_by_env_handler_supports_stage_alias_for_uat() -> None:
    rulebook = load_rulebook_policy()
    legacy_caps = dict(rulebook.caps.max_action_by_env)
    legacy_caps.pop("uat", None)
    legacy_caps["stage"] = "TICKET"
    legacy_rulebook = rulebook.model_copy(
        update={"caps": rulebook.caps.model_copy(update={"max_action_by_env": legacy_caps})}
    )
    ag1 = next(gate for gate in legacy_rulebook.gates if gate.id == "AG1")
    check = next(candidate for candidate in ag1.checks if candidate.type == "cap_by_env")

    result = HANDLER_REGISTRY["cap_by_env"](
        gate_input=_gate_input(),
        rulebook=legacy_rulebook,
        check=check,
        current_action=Action.PAGE,
    )

    assert result.passed is True
    assert result.next_action == Action.TICKET
    assert result.env_cap_applied is True
