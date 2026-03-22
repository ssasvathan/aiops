"""Isolated AG0-AG3 rule-engine execution and startup validation."""

from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.rule_engine.handlers import HANDLER_REGISTRY
from aiops_triage_pipeline.rule_engine.predicates import should_apply_source_topic_page_deny
from aiops_triage_pipeline.rule_engine.protocol import (
    EARLY_GATE_ORDER,
    EarlyGateEvaluation,
    RuleEngineStartupError,
    UnknownCheckTypeStartupError,
)
from aiops_triage_pipeline.rule_engine.safety import (
    apply_gate_effect,
    assert_page_is_limited_to_prod_tier0,
    unique_in_order,
)


def validate_rulebook_handlers(rulebook: RulebookV1) -> None:
    """Fail fast when AG0-AG3 contains unregistered check types."""
    gates_by_id = {gate.id: gate for gate in rulebook.gates}
    for gate_id in EARLY_GATE_ORDER:
        gate = gates_by_id.get(gate_id)
        if gate is None:
            raise RuleEngineStartupError(f"Rulebook is missing required early gate {gate_id!r}")
        for check in gate.checks:
            if check.type in HANDLER_REGISTRY:
                continue
            raise UnknownCheckTypeStartupError(
                gate_id=gate_id,
                check_id=check.check_id,
                check_type=check.type,
            )


def evaluate_gates(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,
    initial_action: Action,
) -> EarlyGateEvaluation:
    """Evaluate AG0-AG3 through the frozen check-handler registry."""
    validate_rulebook_handlers(rulebook)

    gates_by_id = {gate.id: gate for gate in rulebook.gates}
    current_action = initial_action
    input_valid = True
    env_cap_applied = False
    gate_reason_codes: list[str] = []

    for gate_id in EARLY_GATE_ORDER:
        gate_spec = gates_by_id[gate_id]
        if gate_id == "AG3" and not should_apply_source_topic_page_deny(
            gate_input=gate_input,
            rulebook=rulebook,
            current_action=current_action,
        ):
            continue

        gate_start_action = current_action
        gate_failed = False
        gate_env_cap_applied = False

        for check in gate_spec.checks:
            result = HANDLER_REGISTRY[check.type](
                gate_input=gate_input,
                rulebook=rulebook,
                check=check,
                current_action=current_action,
            )
            if result.next_action is not None:
                current_action = result.next_action
            gate_env_cap_applied = gate_env_cap_applied or result.env_cap_applied
            if result.passed:
                continue

            if gate_id == "AG0":
                input_valid = False

            current_action, new_reason_codes = apply_gate_effect(
                current_action=current_action,
                effect=gate_spec.effect.on_fail,
                gate_id=gate_id,
            )
            gate_reason_codes.extend(new_reason_codes)
            gate_failed = True
            break

        if gate_id == "AG1" and not gate_failed and current_action != gate_start_action:
            env_cap_applied = env_cap_applied or gate_env_cap_applied
            current_action, new_reason_codes = apply_gate_effect(
                current_action=current_action,
                effect=gate_spec.effect.on_cap_applied,
                gate_id=gate_id,
            )
            gate_reason_codes.extend(new_reason_codes)

    assert_page_is_limited_to_prod_tier0(gate_input=gate_input, action=current_action)

    return EarlyGateEvaluation(
        current_action=current_action,
        input_valid=input_valid,
        env_cap_applied=env_cap_applied,
        gate_reason_codes=unique_in_order(gate_reason_codes),
    )
