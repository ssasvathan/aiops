"""Safety and monotonic action helpers for isolated AG0-AG3 evaluation."""

from collections.abc import Mapping

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, Environment
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import GateEffect
from aiops_triage_pipeline.rule_engine.protocol import RuleEngineSafetyError

_ACTION_PRIORITY: dict[Action, int] = {
    Action.OBSERVE: 0,
    Action.NOTIFY: 1,
    Action.TICKET: 2,
    Action.PAGE: 3,
}


def action_from_policy_value(value: str, *, context: str) -> Action:
    """Convert a policy string to Action with contextual validation errors."""
    try:
        return Action(value)
    except ValueError as exc:
        raise ValueError(f"Invalid action value {value!r} in {context}") from exc


def reduce_action(current_action: Action, cap_action: Action) -> Action:
    """Apply monotonic cap semantics (never escalate)."""
    if _ACTION_PRIORITY[current_action] <= _ACTION_PRIORITY[cap_action]:
        return current_action
    return cap_action


def apply_gate_effect(
    *,
    current_action: Action,
    effect: GateEffect | None,
    gate_id: str,
) -> tuple[Action, tuple[str, ...]]:
    """Apply AG0-AG3 effect payloads to action/reason-code state."""
    if effect is None:
        return current_action, ()

    next_action = current_action
    if effect.cap_action_to:
        cap_action = action_from_policy_value(
            effect.cap_action_to,
            context=f"{gate_id}.effect.cap_action_to",
        )
        next_action = reduce_action(current_action, cap_action)

    return next_action, effect.set_reason_codes


def unique_in_order(values: list[str]) -> tuple[str, ...]:
    """Return stable-order unique values for deterministic reason-code output."""
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return tuple(unique_values)


def assert_page_is_limited_to_prod_tier0(*, gate_input: GateInputV1, action: Action) -> None:
    """Enforce the invariant: PAGE is impossible outside PROD + TIER_0."""
    if action != Action.PAGE:
        return
    if gate_input.env == Environment.PROD and gate_input.criticality_tier == CriticalityTier.TIER_0:
        return
    raise RuleEngineSafetyError(
        "PAGE must remain structurally impossible outside PROD + TIER_0"
    )


def action_priority() -> Mapping[Action, int]:
    """Expose an immutable view of action priority ordering for callers/tests."""
    return _ACTION_PRIORITY
