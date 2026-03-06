"""Stage 6 gate-input assembly and deterministic rulebook evaluation helpers."""

from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal, Mapping, Protocol

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import GateEffect, GateSpec, RulebookV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput

GateScope = tuple[str, ...]
_EXPECTED_GATE_ORDER: tuple[str, ...] = ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
_ACTION_PRIORITY: dict[Action, int] = {
    Action.OBSERVE: 0,
    Action.NOTIFY: 1,
    Action.TICKET: 2,
    Action.PAGE: 3,
}


@dataclass(frozen=True)
class GateInputContext:
    """Scope context required to build GateInputV1 from stage outputs."""

    stream_id: str
    topic_role: Literal["SOURCE_TOPIC", "SHARED_TOPIC", "SINK_TOPIC"]
    criticality_tier: CriticalityTier
    source_system: str | None = None
    proposed_action: Action = Action.OBSERVE
    diagnosis_confidence: float = 0.0
    partition_count_observed: int | None = None
    case_id: str | None = None
    decision_basis: Mapping[str, Any] | None = None


class GateDedupeStoreProtocol(Protocol):
    """Narrow AG5 dedupe seam to keep Stage 6 deterministic and testable."""

    def is_duplicate(self, fingerprint: str) -> bool:
        """Return True when the fingerprint is already active in the dedupe window."""

    def remember(self, fingerprint: str, action: Action) -> None:
        """Persist fingerprint in dedupe window with the per-action TTL."""


@dataclass
class _EvaluationState:
    current_action: Action
    input_valid: bool = True
    env_cap_applied: bool = False
    gate_reason_codes: list[str] = field(default_factory=list)
    postmortem_required: bool = False
    postmortem_mode: str | None = None
    postmortem_reason_codes: list[str] = field(default_factory=list)


def evaluate_rulebook_gates(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,
    dedupe_store: GateDedupeStoreProtocol | None = None,
    latency_warning_threshold_ms: int = 500,
) -> ActionDecisionV1:
    """Evaluate AG0..AG6 sequentially and return ActionDecisionV1."""
    logger = get_logger("pipeline.stages.gating")
    started = perf_counter()
    _validate_rulebook_gate_order(rulebook.gates)

    state = _EvaluationState(current_action=gate_input.proposed_action)
    gate_specs = {gate.id: gate for gate in rulebook.gates}

    for gate_id in _EXPECTED_GATE_ORDER:
        gate_spec = gate_specs[gate_id]

        if gate_id == "AG0":
            if not _ag0_is_valid(gate_input):
                state.input_valid = False
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_fail,
                    gate_id=gate_id,
                )
            continue

        if gate_id == "AG1":
            _evaluate_ag1(
                gate_input=gate_input,
                rulebook=rulebook,
                gate_spec=gate_spec,
                state=state,
            )
            continue

        if gate_id == "AG2":
            if _ag2_has_insufficient_evidence(gate_input):
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_fail,
                    gate_id=gate_id,
                )
            continue

        if gate_id == "AG3":
            if (
                gate_input.topic_role in rulebook.caps.paging_denied_topic_roles
                and state.current_action == Action.PAGE
            ):
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_fail,
                    gate_id=gate_id,
                )
            continue

        if gate_id == "AG4":
            if _ACTION_PRIORITY[state.current_action] < _ACTION_PRIORITY[Action.TICKET]:
                continue
            ag4_reason_codes = _ag4_failure_reason_codes(
                gate_spec=gate_spec,
                gate_input=gate_input,
            )
            if ag4_reason_codes:
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_fail,
                    gate_id=gate_id,
                )
                state.gate_reason_codes.extend(ag4_reason_codes)
            continue

        if gate_id == "AG5":
            if _ACTION_PRIORITY[state.current_action] <= _ACTION_PRIORITY[Action.OBSERVE]:
                continue
            if dedupe_store is None:
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_store_error,
                    gate_id=gate_id,
                )
                continue
            try:
                if dedupe_store.is_duplicate(gate_input.action_fingerprint):
                    _apply_gate_effect(
                        state=state,
                        effect=gate_spec.effect.on_duplicate,
                        gate_id=gate_id,
                    )
                else:
                    dedupe_store.remember(gate_input.action_fingerprint, state.current_action)
            except Exception:
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_store_error,
                    gate_id=gate_id,
                )
            continue

        if gate_id == "AG6":
            if (
                state.input_valid
                and gate_input.env == Environment.PROD
                and gate_input.criticality_tier == CriticalityTier.TIER_0
            ):
                if gate_input.peak is True and gate_input.sustained:
                    _apply_gate_effect(
                        state=state,
                        effect=gate_spec.effect.on_pass,
                        gate_id=gate_id,
                        allow_action_change=False,
                    )
                else:
                    _apply_gate_effect(
                        state=state,
                        effect=gate_spec.effect.on_fail,
                        gate_id=gate_id,
                        allow_action_change=False,
                    )

    state.gate_reason_codes = list(_unique_in_order(state.gate_reason_codes))
    state.postmortem_reason_codes = list(_unique_in_order(state.postmortem_reason_codes))
    if state.postmortem_required and state.postmortem_mode is None:
        state.postmortem_mode = "SOFT"
    if not state.postmortem_required:
        state.postmortem_mode = None
        state.postmortem_reason_codes = []

    elapsed_ms = (perf_counter() - started) * 1000.0
    logger.info(
        "rulebook_gate_evaluation_completed",
        event_type="gating.rulebook_evaluation",
        evaluation_duration_ms=round(elapsed_ms, 3),
        final_action=state.current_action.value,
        gate_rule_ids=_EXPECTED_GATE_ORDER,
        gate_reason_codes=tuple(state.gate_reason_codes),
        action_fingerprint=gate_input.action_fingerprint,
    )
    if elapsed_ms > latency_warning_threshold_ms:
        logger.warning(
            "rulebook_gate_evaluation_slow",
            event_type="gating.rulebook_latency_guardrail_exceeded",
            evaluation_duration_ms=round(elapsed_ms, 3),
            latency_warning_threshold_ms=latency_warning_threshold_ms,
            action_fingerprint=gate_input.action_fingerprint,
        )

    return ActionDecisionV1(
        final_action=state.current_action,
        env_cap_applied=state.env_cap_applied,
        gate_rule_ids=_EXPECTED_GATE_ORDER,
        gate_reason_codes=tuple(state.gate_reason_codes),
        action_fingerprint=gate_input.action_fingerprint,
        postmortem_required=state.postmortem_required,
        postmortem_mode=state.postmortem_mode,
        postmortem_reason_codes=tuple(state.postmortem_reason_codes),
    )


def evaluate_rulebook_gate_inputs_by_scope(
    *,
    gate_inputs_by_scope: Mapping[GateScope, tuple[GateInputV1, ...]],
    rulebook: RulebookV1,
    dedupe_store: GateDedupeStoreProtocol | None = None,
    latency_warning_threshold_ms: int = 500,
) -> dict[GateScope, tuple[ActionDecisionV1, ...]]:
    """Evaluate all gate inputs and return ActionDecisionV1 payloads by scope."""
    decisions_by_scope: dict[GateScope, tuple[ActionDecisionV1, ...]] = {}
    for scope, gate_inputs in sorted(gate_inputs_by_scope.items()):
        decisions_by_scope[scope] = tuple(
            evaluate_rulebook_gates(
                gate_input=gate_input,
                rulebook=rulebook,
                dedupe_store=dedupe_store,
                latency_warning_threshold_ms=latency_warning_threshold_ms,
            )
            for gate_input in gate_inputs
        )
    return decisions_by_scope


def collect_gate_inputs_by_scope(
    *,
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    context_by_scope: Mapping[GateScope, GateInputContext],
    max_safe_action: Action | None = None,
) -> dict[GateScope, tuple[GateInputV1, ...]]:
    """Build GateInputV1 payloads grouped by normalized anomaly scope."""
    logger = get_logger("pipeline.stages.gating")
    gate_inputs_by_scope: dict[GateScope, list[GateInputV1]] = defaultdict(list)

    for scope, findings in sorted(evidence_output.gate_findings_by_scope.items()):
        context = _resolve_context_for_scope(scope=scope, context_by_scope=context_by_scope)
        if context is None:
            raise KeyError(
                f"Missing gate-input context for scope={scope} "
                "(or topic scope fallback for group-based scope)"
            )

        topic = _topic_from_scope(scope)
        consumer_group = _consumer_group_from_scope(scope)
        env = Environment(scope[0])
        cluster_id = scope[1]
        evidence_status_map = dict(evidence_output.evidence_status_map_by_scope.get(scope, {}))
        peak_context = peak_output.peak_context_by_scope.get((env.value, cluster_id, topic))
        peak = peak_context.is_peak_window if peak_context is not None else None

        for finding in findings:
            anomaly_family = _anomaly_family_from_gate_finding_name(finding.name)
            sustained_key = _sustained_identity_key(
                scope=scope,
                anomaly_family=anomaly_family,
            )
            sustained_status = peak_output.sustained_by_key.get(sustained_key)
            sustained = sustained_status.is_sustained if sustained_status is not None else False

            gate_inputs_by_scope[scope].append(
                GateInputV1(
                    env=env,
                    cluster_id=cluster_id,
                    stream_id=context.stream_id,
                    topic=topic,
                    topic_role=context.topic_role,
                    anomaly_family=anomaly_family,
                    criticality_tier=context.criticality_tier,
                    proposed_action=_cap_action_to_max_safe(
                        proposed_action=context.proposed_action,
                        max_safe_action=max_safe_action,
                    ),
                    diagnosis_confidence=context.diagnosis_confidence,
                    sustained=sustained,
                    findings=tuple(findings),
                    evidence_status_map=evidence_status_map,
                    action_fingerprint=_action_fingerprint(
                        env=env.value,
                        cluster_id=cluster_id,
                        stream_id=context.stream_id,
                        topic_role=context.topic_role,
                        topic=topic,
                        anomaly_family=anomaly_family,
                        criticality_tier=context.criticality_tier.value,
                        consumer_group=consumer_group,
                    ),
                    consumer_group=consumer_group,
                    partition_count_observed=context.partition_count_observed,
                    peak=peak,
                    case_id=context.case_id,
                    decision_basis=(
                        dict(context.decision_basis)
                        if context.decision_basis is not None
                        else None
                    ),
                )
            )

    if not gate_inputs_by_scope:
        logger.info(
            "gate_input_assembly_no_findings",
            event_type="gating.no_findings",
        )

    return {
        scope: tuple(scope_gate_inputs)
        for scope, scope_gate_inputs in sorted(gate_inputs_by_scope.items())
    }


def _validate_rulebook_gate_order(gates: tuple[GateSpec, ...]) -> None:
    gate_ids = tuple(gate.id for gate in gates)
    if gate_ids != _EXPECTED_GATE_ORDER:
        raise ValueError(
            f"Rulebook gate order must be {_EXPECTED_GATE_ORDER}; got {gate_ids}"
        )


def _ag0_is_valid(gate_input: GateInputV1) -> bool:
    if not gate_input.action_fingerprint.strip():
        return False
    if not gate_input.findings:
        return False
    return True


def _evaluate_ag1(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,
    gate_spec: GateSpec,
    state: _EvaluationState,
) -> None:
    env_cap = _lookup_action_policy_entry(
        mapping=rulebook.caps.max_action_by_env,
        key=gate_input.env.value,
        context="caps.max_action_by_env",
        fallback_keys=_env_policy_fallback_keys(gate_input.env.value),
    )
    env_capped_action = _reduce_action(state.current_action, env_cap)
    env_cap_reduced_action = env_capped_action != state.current_action
    capped_action = env_capped_action
    if gate_input.env == Environment.PROD:
        prod_tier_cap = _lookup_action_policy_entry(
            mapping=rulebook.caps.max_action_by_tier_in_prod,
            key=gate_input.criticality_tier.value,
            context="caps.max_action_by_tier_in_prod",
        )
        capped_action = _reduce_action(capped_action, prod_tier_cap)

    cap_reduced_action = capped_action != state.current_action
    if cap_reduced_action:
        state.current_action = capped_action
        if env_cap_reduced_action:
            state.env_cap_applied = True
        _apply_gate_effect(
            state=state,
            effect=gate_spec.effect.on_cap_applied,
            gate_id="AG1",
            mark_env_cap_applied=env_cap_reduced_action,
        )


def _ag2_has_insufficient_evidence(gate_input: GateInputV1) -> bool:
    anomalous_findings = [finding for finding in gate_input.findings if finding.is_anomalous]
    if not anomalous_findings:
        return False

    findings_to_check = [finding for finding in anomalous_findings if finding.is_primary]
    if not findings_to_check:
        findings_to_check = anomalous_findings

    for finding in findings_to_check:
        for required_evidence in finding.evidence_required:
            status = gate_input.evidence_status_map.get(required_evidence, EvidenceStatus.UNKNOWN)
            if status == EvidenceStatus.PRESENT:
                continue
            allowed_non_present_statuses = finding.allowed_non_present_statuses_by_evidence.get(
                required_evidence,
                (),
            )
            if status in allowed_non_present_statuses:
                continue
            return True
    return False


def _ag4_failure_reason_codes(*, gate_spec: GateSpec, gate_input: GateInputV1) -> tuple[str, ...]:
    reason_codes: list[str] = []
    found_confidence_check = False
    found_sustained_check = False

    for check in gate_spec.checks:
        model_extra = check.model_extra or {}
        field_name = model_extra.get("field")

        if check.type == "min_value" and field_name == "diagnosis_confidence":
            found_confidence_check = True
            min_value = model_extra.get("min")
            if not isinstance(min_value, int | float):
                raise ValueError(
                    "AG4 diagnosis_confidence min_value check is missing numeric min threshold"
                )
            if gate_input.diagnosis_confidence < float(min_value):
                reason_codes.append(
                    _ag4_reason_code_from_check(
                        model_extra=model_extra,
                        default_code="LOW_CONFIDENCE",
                    )
                )
            continue

        if check.type == "equals" and field_name == "sustained":
            found_sustained_check = True
            expected_value = model_extra.get("value")
            if not isinstance(expected_value, bool):
                raise ValueError("AG4 sustained equals check must define a boolean value")
            if gate_input.sustained != expected_value:
                reason_codes.append(
                    _ag4_reason_code_from_check(
                        model_extra=model_extra,
                        default_code="NOT_SUSTAINED",
                    )
                )

    if not found_confidence_check:
        raise ValueError("AG4 is missing diagnosis_confidence min_value check configuration")
    if not found_sustained_check:
        raise ValueError("AG4 is missing sustained equals check configuration")

    return _unique_in_order(reason_codes)


def _ag4_reason_code_from_check(*, model_extra: Mapping[str, Any], default_code: str) -> str:
    reason_code = model_extra.get("reason_code_on_fail")
    if isinstance(reason_code, str):
        normalized = reason_code.strip()
        if normalized:
            return normalized
    return default_code


def _lookup_action_policy_entry(
    *,
    mapping: Mapping[str, str],
    key: str,
    context: str,
    fallback_keys: tuple[str, ...] = (),
) -> Action:
    candidate_keys = (key,) + fallback_keys
    for candidate_key in candidate_keys:
        policy_value = mapping.get(candidate_key)
        if policy_value is None:
            continue
        return _action_from_policy_value(policy_value, context=f"{context}[{candidate_key!r}]")
    raise ValueError(f"Missing policy mapping for {context}[{key!r}]")


def _env_policy_fallback_keys(env_key: str) -> tuple[str, ...]:
    # Backward compatibility while policy artifacts migrate from `stage` to `uat`.
    if env_key == "uat":
        return ("stage",)
    if env_key == "stage":
        return ("uat",)
    return ()


def _action_from_policy_value(value: str, *, context: str) -> Action:
    try:
        return Action(value)
    except ValueError as exc:
        raise ValueError(f"Invalid action value {value!r} in {context}") from exc


def _apply_gate_effect(
    *,
    state: _EvaluationState,
    effect: GateEffect | None,
    gate_id: str,
    allow_action_change: bool = True,
    mark_env_cap_applied: bool = False,
) -> None:
    if effect is None:
        return

    if effect.cap_action_to and allow_action_change:
        cap_action = _action_from_policy_value(
            effect.cap_action_to,
            context=f"{gate_id}.effect.cap_action_to",
        )
        reduced_action = _reduce_action(state.current_action, cap_action)
        if reduced_action != state.current_action and mark_env_cap_applied:
            state.env_cap_applied = True
        state.current_action = reduced_action

    state.gate_reason_codes.extend(effect.set_reason_codes)

    if effect.force_postmortem_mode is not None:
        mode = effect.force_postmortem_mode.strip().upper()
        state.postmortem_mode = None if mode in {"", "NONE"} else mode
    if effect.set_postmortem_required is not None:
        state.postmortem_required = effect.set_postmortem_required
    state.postmortem_reason_codes.extend(effect.set_postmortem_reason_codes)


def _reduce_action(current_action: Action, cap_action: Action) -> Action:
    if _ACTION_PRIORITY[current_action] <= _ACTION_PRIORITY[cap_action]:
        return current_action
    return cap_action


def _unique_in_order(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return tuple(unique_values)


def _resolve_context_for_scope(
    *,
    scope: GateScope,
    context_by_scope: Mapping[GateScope, GateInputContext],
) -> GateInputContext | None:
    context = context_by_scope.get(scope)
    if context is not None:
        return context

    if len(scope) == 4:
        topic_scope = (scope[0], scope[1], scope[3])
        return context_by_scope.get(topic_scope)

    return None


def _anomaly_family_from_gate_finding_name(
    finding_name: str,
) -> Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]:
    normalized = finding_name.strip().upper()
    if normalized == "CONSUMER_LAG":
        return "CONSUMER_LAG"
    if normalized == "VOLUME_DROP":
        return "VOLUME_DROP"
    if normalized == "THROUGHPUT_CONSTRAINED_PROXY":
        return "THROUGHPUT_CONSTRAINED_PROXY"
    raise ValueError(f"Unsupported finding name for anomaly family mapping: {finding_name!r}")


def _topic_from_scope(scope: GateScope) -> str:
    if len(scope) == 3:
        return scope[2]
    if len(scope) == 4:
        return scope[3]
    raise ValueError(f"Unsupported scope shape for topic extraction: {scope}")


def _consumer_group_from_scope(scope: GateScope) -> str | None:
    if len(scope) == 4:
        return scope[2]
    return None


def _sustained_identity_key(
    *,
    scope: GateScope,
    anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"],
) -> tuple[str, str, str, str]:
    if len(scope) == 3:
        return (scope[0], scope[1], f"topic:{scope[2]}", anomaly_family)
    if len(scope) == 4:
        return (scope[0], scope[1], f"group:{scope[2]}", anomaly_family)
    raise ValueError(f"Unsupported scope shape for sustained identity key: {scope}")


def _action_fingerprint(
    *,
    env: str,
    cluster_id: str,
    stream_id: str,
    topic_role: str,
    topic: str,
    anomaly_family: str,
    criticality_tier: str,
    consumer_group: str | None,
) -> str:
    parts = [
        env,
        cluster_id,
        stream_id,
        topic_role,
        topic,
        anomaly_family,
        criticality_tier,
    ]
    if consumer_group is not None:
        parts.append(f"group:{consumer_group}")
    return "/".join(parts)


def _cap_action_to_max_safe(*, proposed_action: Action, max_safe_action: Action | None) -> Action:
    if max_safe_action is None:
        return proposed_action
    if _ACTION_PRIORITY[proposed_action] <= _ACTION_PRIORITY[max_safe_action]:
        return proposed_action
    return max_safe_action
