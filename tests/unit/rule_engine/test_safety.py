import pytest

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, Environment
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import GateEffect
from aiops_triage_pipeline.rule_engine.protocol import RuleEngineSafetyError
from aiops_triage_pipeline.rule_engine.safety import (
    apply_gate_effect,
    assert_page_is_limited_to_prod_tier0,
    reduce_action,
)


def _gate_input() -> GateInputV1:
    return GateInputV1.model_validate(
        {
            "env": "prod",
            "cluster_id": "cluster-a",
            "stream_id": "stream-orders",
            "topic": "orders",
            "topic_role": "SHARED_TOPIC",
            "anomaly_family": "VOLUME_DROP",
            "criticality_tier": "TIER_0",
            "proposed_action": "PAGE",
            "diagnosis_confidence": 0.95,
            "sustained": True,
            "findings": [
                {
                    "finding_id": "f-1",
                    "name": "volume-drop",
                    "is_anomalous": True,
                    "evidence_required": ["topic_messages_in_per_sec"],
                }
            ],
            "evidence_status_map": {"topic_messages_in_per_sec": "PRESENT"},
            "action_fingerprint": (
                "prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0"
            ),
        }
    )


def test_reduce_action_is_monotonic() -> None:
    assert reduce_action(Action.OBSERVE, Action.PAGE) == Action.OBSERVE
    assert reduce_action(Action.PAGE, Action.NOTIFY) == Action.NOTIFY


def test_apply_gate_effect_caps_action_and_preserves_reason_code_order() -> None:
    action, reason_codes = apply_gate_effect(
        current_action=Action.PAGE,
        effect=GateEffect(
            cap_action_to="NOTIFY",
            set_reason_codes=("CODE_A", "CODE_B"),
        ),
        gate_id="AGX",
    )

    assert action == Action.NOTIFY
    assert reason_codes == ("CODE_A", "CODE_B")


def test_assert_page_is_limited_to_prod_tier0() -> None:
    assert_page_is_limited_to_prod_tier0(
        gate_input=_gate_input(),
        action=Action.PAGE,
    )

    with pytest.raises(RuleEngineSafetyError, match=r"outside PROD \+ TIER_0"):
        assert_page_is_limited_to_prod_tier0(
            gate_input=_gate_input().model_copy(
                update={
                    "env": Environment.DEV,
                    "criticality_tier": CriticalityTier.TIER_0,
                }
            ),
            action=Action.PAGE,
        )
