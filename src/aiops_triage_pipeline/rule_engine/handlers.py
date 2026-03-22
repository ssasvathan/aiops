"""AG0-AG3 check handlers and frozen check-type registry."""

from types import MappingProxyType

from aiops_triage_pipeline.contracts.enums import Environment
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import GateCheck, RulebookV1
from aiops_triage_pipeline.rule_engine.predicates import (
    env_policy_fallback_keys,
    has_required_fields_present,
    has_sufficient_required_evidence,
    lookup_action_policy_entry,
    resolve_action_mapping,
)
from aiops_triage_pipeline.rule_engine.protocol import CheckResult, GateCheckHandler
from aiops_triage_pipeline.rule_engine.safety import reduce_action


def _required_str_extra(*, check: GateCheck, key: str) -> str:
    model_extra = check.model_extra or {}
    raw_value = model_extra.get(key)
    if not isinstance(raw_value, str):
        raise ValueError(f"{check.check_id} is missing required {key!r} metadata")
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{check.check_id} has blank {key!r} metadata")
    return normalized


def _required_fields_present_handler(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,  # noqa: ARG001
    check: GateCheck,  # noqa: ARG001
    current_action,
) -> CheckResult:
    return CheckResult(passed=has_required_fields_present(gate_input), next_action=current_action)


def _cap_by_env_handler(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,
    check: GateCheck,
    current_action,
) -> CheckResult:
    mapping_ref = _required_str_extra(check=check, key="max_action_by_env_ref")
    env_mapping = resolve_action_mapping(rulebook=rulebook, mapping_ref=mapping_ref)
    env_cap = lookup_action_policy_entry(
        mapping=env_mapping,
        key=gate_input.env.value,
        context=mapping_ref,
        fallback_keys=env_policy_fallback_keys(gate_input.env.value),
    )
    next_action = reduce_action(current_action, env_cap)
    return CheckResult(
        passed=True,
        next_action=next_action,
        env_cap_applied=next_action != current_action,
    )


def _cap_by_tier_in_prod_handler(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,
    check: GateCheck,
    current_action,
) -> CheckResult:
    if gate_input.env != Environment.PROD:
        return CheckResult(passed=True, next_action=current_action)

    mapping_ref = _required_str_extra(check=check, key="max_action_by_tier_ref")
    tier_mapping = resolve_action_mapping(rulebook=rulebook, mapping_ref=mapping_ref)
    tier_cap = lookup_action_policy_entry(
        mapping=tier_mapping,
        key=gate_input.criticality_tier.value,
        context=mapping_ref,
    )
    next_action = reduce_action(current_action, tier_cap)
    return CheckResult(passed=True, next_action=next_action)


def _required_evidence_present_handler(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,  # noqa: ARG001
    check: GateCheck,  # noqa: ARG001
    current_action,
) -> CheckResult:
    return CheckResult(
        passed=has_sufficient_required_evidence(gate_input),
        next_action=current_action,
    )


def _always_fail_handler(
    *,
    gate_input: GateInputV1,  # noqa: ARG001
    rulebook: RulebookV1,  # noqa: ARG001
    check: GateCheck,  # noqa: ARG001
    current_action,
) -> CheckResult:
    return CheckResult(passed=False, next_action=current_action)


def _always_pass_handler(
    *,
    gate_input: GateInputV1,  # noqa: ARG001
    rulebook: RulebookV1,  # noqa: ARG001
    check: GateCheck,  # noqa: ARG001
    current_action,
) -> CheckResult:
    return CheckResult(passed=True, next_action=current_action)


HANDLER_REGISTRY: MappingProxyType[str, GateCheckHandler] = MappingProxyType(
    {
        "required_fields_present": _required_fields_present_handler,
        "cap_by_env": _cap_by_env_handler,
        "cap_by_tier_in_prod": _cap_by_tier_in_prod_handler,
        "required_evidence_present": _required_evidence_present_handler,
        "always_fail": _always_fail_handler,
        "always_pass": _always_pass_handler,
    }
)
