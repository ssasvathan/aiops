import pytest

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy
from aiops_triage_pipeline.rule_engine.engine import (
    evaluate_gates,
    validate_rulebook_handlers,
)
from aiops_triage_pipeline.rule_engine.protocol import (
    RuleEngineSafetyError,
    UnknownCheckTypeStartupError,
)


def _gate_input() -> GateInputV1:
    return GateInputV1(
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role="SOURCE_TOPIC",
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
        action_fingerprint="prod/cluster-a/stream-orders/SOURCE_TOPIC/orders/VOLUME_DROP/TIER_0",
        peak=True,
    )


def test_evaluate_gates_applies_ag3_source_topic_deny_with_deterministic_reason_codes() -> None:
    result = evaluate_gates(
        gate_input=_gate_input(),
        rulebook=load_rulebook_policy(),
        initial_action=Action.PAGE,
    )

    assert result.current_action == Action.TICKET
    assert result.input_valid is True
    assert result.env_cap_applied is False
    assert result.gate_reason_codes == ("AG3_PAGING_DENIED_SOURCE_TOPIC",)


def test_evaluate_gates_ag2_insufficient_evidence_short_circuits_before_ag3() -> None:
    gate_input = _gate_input().model_copy(
        update={"evidence_status_map": {"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN}}
    )

    result = evaluate_gates(
        gate_input=gate_input,
        rulebook=load_rulebook_policy(),
        initial_action=Action.PAGE,
    )

    assert result.current_action == Action.NOTIFY
    assert "AG2_INSUFFICIENT_EVIDENCE" in result.gate_reason_codes
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" not in result.gate_reason_codes


def test_validate_rulebook_handlers_raises_for_unknown_check_type() -> None:
    rulebook = load_rulebook_policy()
    ag0 = next(gate for gate in rulebook.gates if gate.id == "AG0")
    bad_ag0 = ag0.model_copy(
        update={
            "checks": (
                ag0.checks[0].model_copy(update={"type": "missing_handler_type"}),
            )
        }
    )
    bad_rulebook = rulebook.model_copy(
        update={
            "gates": tuple(bad_ag0 if gate.id == "AG0" else gate for gate in rulebook.gates)
        }
    )

    with pytest.raises(UnknownCheckTypeStartupError, match="missing_handler_type"):
        validate_rulebook_handlers(bad_rulebook)


def test_evaluate_gates_raises_when_page_remains_possible_outside_prod_tier0() -> None:
    rulebook = load_rulebook_policy()
    caps = rulebook.caps.model_copy(
        update={
            "max_action_by_env": {
                **rulebook.caps.max_action_by_env,
                "dev": "PAGE",
            }
        }
    )
    unsafe_rulebook = rulebook.model_copy(update={"caps": caps})

    with pytest.raises(RuleEngineSafetyError, match=r"outside PROD \+ TIER_0"):
        evaluate_gates(
            gate_input=_gate_input().model_copy(
                update={
                    "env": Environment.DEV,
                    "criticality_tier": CriticalityTier.TIER_0,
                    "topic_role": "SHARED_TOPIC",
                }
            ),
            rulebook=unsafe_rulebook,
            initial_action=Action.PAGE,
        )
