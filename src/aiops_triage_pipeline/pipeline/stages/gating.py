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
from aiops_triage_pipeline.rule_engine import evaluate_gates

GateScope = tuple[str, ...]
_EXPECTED_GATE_ORDER: tuple[str, ...] = ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
_ACTION_PRIORITY: dict[Action, int] = {
    Action.OBSERVE: 0,
    Action.NOTIFY: 1,
    Action.TICKET: 2,
    Action.PAGE: 3,
}

SCORE_V1_VERSION = "v1"
SCORE_V1_BASE_PRESENT_WEIGHT = 1.0
SCORE_V1_BASE_UNKNOWN_WEIGHT = 0.25
SCORE_V1_BASE_ABSENT_WEIGHT = 0.0
SCORE_V1_BASE_STALE_WEIGHT = 0.0
SCORE_V1_SUSTAINED_AMPLIFIER_MAX = 0.08
SCORE_V1_PEAK_AMPLIFIER = 0.05
SCORE_V1_NEAR_PEAK_AMPLIFIER = 0.03
SCORE_V1_ACTION_BAND_TICKET_MIN = 0.60
SCORE_V1_ACTION_BAND_PAGE_MIN = 0.85
SCORE_V1_DECIMAL_PRECISION = 6


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

    def remember(self, fingerprint: str, action: Action) -> bool:
        """Persist fingerprint in dedupe window with the per-action TTL.

        Returns True if the key was newly registered, False if it already existed
        (e.g. a concurrent worker won the atomic NX claim first).
        """


@dataclass
class _EvaluationState:
    current_action: Action
    input_valid: bool = True
    env_cap_applied: bool = False
    gate_reason_codes: list[str] = field(default_factory=list)
    postmortem_required: bool = False
    postmortem_mode: str | None = None
    postmortem_reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ScoringResult:
    base_score: float
    sustained_boost: float
    peak_boost: float
    final_score: float
    proposed_action: Action
    score_reason_code: str
    fallback_applied: bool = False


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
    early_gate_result = evaluate_gates(
        gate_input=gate_input,
        rulebook=rulebook,
        initial_action=state.current_action,
    )
    state.current_action = early_gate_result.current_action
    state.input_valid = early_gate_result.input_valid
    state.env_cap_applied = early_gate_result.env_cap_applied
    state.gate_reason_codes.extend(early_gate_result.gate_reason_codes)

    for gate_id in _EXPECTED_GATE_ORDER[4:]:
        gate_spec = gate_specs[gate_id]

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
                registered = dedupe_store.remember(
                    gate_input.action_fingerprint,
                    state.current_action,
                )
                if not registered:
                    _apply_gate_effect(
                        state=state,
                        effect=gate_spec.effect.on_duplicate,
                        gate_id=gate_id,
                    )
            except Exception as exc:
                logger.warning(
                    "ag5_dedupe_store_error",
                    event_type="gating.ag5_store_error",
                    action_fingerprint=gate_input.action_fingerprint,
                    error=str(exc),
                )
                _apply_gate_effect(
                    state=state,
                    effect=gate_spec.effect.on_store_error,
                    gate_id=gate_id,
                )
            continue

        if gate_id == "AG6":
            # AG6 only evaluates PM_PEAK_SUSTAINED for PROD + TIER_0 inputs.
            # For other envs/tiers, neither on_pass nor on_fail is applied;
            # postmortem fields retain their _EvaluationState defaults (False/None/()).
            if (
                state.input_valid
                and gate_input.env == Environment.PROD
                and gate_input.criticality_tier == CriticalityTier.TIER_0
            ):
                # peak is True uses strict identity: peak=None (UNKNOWN) must not fire.
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
            is_sustained_for_scoring: bool | None = (
                sustained_status.is_sustained if sustained_status is not None else None
            )
            sustained_for_gate_input = is_sustained_for_scoring is True

            try:
                scoring_result = _derive_scoring_result(
                    evidence_status_map=evidence_status_map,
                    is_sustained=is_sustained_for_scoring,
                    sustained_consecutive_buckets=(
                        sustained_status.consecutive_anomalous_buckets
                        if sustained_status is not None
                        else None
                    ),
                    sustained_required_buckets=(
                        sustained_status.required_buckets
                        if sustained_status is not None
                        else None
                    ),
                    is_peak_window=(
                        peak_context.is_peak_window if peak_context is not None else None
                    ),
                    is_near_peak_window=(
                        peak_context.is_near_peak_window if peak_context is not None else None
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "gating_scoring_fallback_applied",
                    event_type="gating.scoring.fallback_applied",
                    scope=scope,
                    anomaly_family=anomaly_family,
                    error=str(exc),
                )
                scoring_result = _fallback_scoring_result()

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
                        proposed_action=scoring_result.proposed_action,
                        max_safe_action=max_safe_action,
                    ),
                    diagnosis_confidence=scoring_result.final_score,
                    sustained=sustained_for_gate_input,
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
                    decision_basis=_merge_decision_basis(
                        existing_decision_basis=context.decision_basis,
                        scoring_result=scoring_result,
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


def _derive_scoring_result(
    *,
    evidence_status_map: Mapping[str, EvidenceStatus],
    is_sustained: bool | None,
    sustained_consecutive_buckets: int | None,
    sustained_required_buckets: int | None,
    is_peak_window: bool | None,
    is_near_peak_window: bool | None,
) -> _ScoringResult:
    base_score = _score_base_from_evidence_status_map(evidence_status_map)
    sustained_boost = _score_sustained_boost(
        is_sustained=is_sustained,
        consecutive_buckets=sustained_consecutive_buckets,
        required_buckets=sustained_required_buckets,
    )
    peak_boost = _score_peak_boost(
        is_peak_window=is_peak_window,
        is_near_peak_window=is_near_peak_window,
    )
    final_score = _score_final(
        base_score=base_score,
        sustained_boost=sustained_boost,
        peak_boost=peak_boost,
    )
    proposed_action = _derive_proposed_action_from_score(final_score)
    score_reason_code = _derive_score_reason_code(
        final_score=final_score,
        sustained_boost=sustained_boost,
        peak_boost=peak_boost,
    )

    return _ScoringResult(
        base_score=base_score,
        sustained_boost=sustained_boost,
        peak_boost=peak_boost,
        final_score=final_score,
        proposed_action=proposed_action,
        score_reason_code=score_reason_code,
        fallback_applied=False,
    )


def _score_base_from_evidence_status_map(
    evidence_status_map: Mapping[str, EvidenceStatus],
) -> float:
    if not evidence_status_map:
        return 0.0

    weighted_total = 0.0
    for status in evidence_status_map.values():
        weighted_total += _score_weight_for_evidence_status(status)
    return _clamp_score(weighted_total / float(len(evidence_status_map)))


def _score_weight_for_evidence_status(status: EvidenceStatus) -> float:
    if status == EvidenceStatus.PRESENT:
        return SCORE_V1_BASE_PRESENT_WEIGHT
    if status == EvidenceStatus.UNKNOWN:
        return SCORE_V1_BASE_UNKNOWN_WEIGHT
    if status == EvidenceStatus.ABSENT:
        return SCORE_V1_BASE_ABSENT_WEIGHT
    if status == EvidenceStatus.STALE:
        return SCORE_V1_BASE_STALE_WEIGHT
    raise ValueError(f"Unsupported evidence status for scoring: {status!r}")


def _score_sustained_boost(
    is_sustained: bool | None,
    *,
    consecutive_buckets: int | None = None,
    required_buckets: int | None = None,
) -> float:
    if is_sustained is not True:
        return 0.0

    if (
        consecutive_buckets is None
        or required_buckets is None
        or required_buckets <= 0
    ):
        return SCORE_V1_SUSTAINED_AMPLIFIER_MAX

    sustained_ratio = _clamp_score(consecutive_buckets / float(required_buckets))
    return _clamp_score(SCORE_V1_SUSTAINED_AMPLIFIER_MAX * sustained_ratio)


def _score_peak_boost(*, is_peak_window: bool | None, is_near_peak_window: bool | None) -> float:
    if is_peak_window is True:
        return SCORE_V1_PEAK_AMPLIFIER
    if is_near_peak_window is True:
        return SCORE_V1_NEAR_PEAK_AMPLIFIER
    return 0.0


def _score_final(*, base_score: float, sustained_boost: float, peak_boost: float) -> float:
    return _clamp_score(base_score + sustained_boost + peak_boost)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), SCORE_V1_DECIMAL_PRECISION)


def _derive_proposed_action_from_score(score: float) -> Action:
    if score < SCORE_V1_ACTION_BAND_TICKET_MIN:
        return Action.OBSERVE
    if score < SCORE_V1_ACTION_BAND_PAGE_MIN:
        return Action.TICKET
    return Action.PAGE


def _derive_score_reason_code(
    *,
    final_score: float,
    sustained_boost: float,
    peak_boost: float,
) -> str:
    if final_score < SCORE_V1_ACTION_BAND_TICKET_MIN:
        return "LOW_CONFIDENCE_INSUFFICIENT_EVIDENCE"
    if final_score >= SCORE_V1_ACTION_BAND_PAGE_MIN:
        if sustained_boost > 0.0 and peak_boost > 0.0:
            return "HIGH_CONFIDENCE_SUSTAINED_PEAK"
        if sustained_boost > 0.0:
            return "HIGH_CONFIDENCE_SUSTAINED"
        return "HIGH_CONFIDENCE"
    if sustained_boost > 0.0 and peak_boost > 0.0:
        return "MEDIUM_CONFIDENCE_SUSTAINED_PEAK"
    if sustained_boost > 0.0:
        return "MEDIUM_CONFIDENCE_SUSTAINED"
    return "MEDIUM_CONFIDENCE_BASELINE"


def _fallback_scoring_result() -> _ScoringResult:
    return _ScoringResult(
        base_score=0.0,
        sustained_boost=0.0,
        peak_boost=0.0,
        final_score=0.0,
        proposed_action=Action.OBSERVE,
        score_reason_code="SCORING_FALLBACK_APPLIED",
        fallback_applied=True,
    )


def _merge_decision_basis(
    *,
    existing_decision_basis: Mapping[str, Any] | None,
    scoring_result: _ScoringResult,
) -> dict[str, Any]:
    decision_basis = (
        dict(existing_decision_basis)
        if existing_decision_basis is not None
        else {}
    )
    decision_basis.update(
        {
            "score_version": SCORE_V1_VERSION,
            "base_score": scoring_result.base_score,
            "sustained_boost": scoring_result.sustained_boost,
            "peak_boost": scoring_result.peak_boost,
            "final_score": scoring_result.final_score,
            "score_reason_code": scoring_result.score_reason_code,
            "fallback_applied": scoring_result.fallback_applied,
        }
    )
    return decision_basis


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
    # NOTE: effect.confidence_floor is parsed by GateEffect but intentionally not
    # enforced here — it is a gate-engine reserved field for a future evidence-confidence
    # floor mechanism. It is NOT the LLM confidence input vector and has no connection
    # to any cold-path (LLM) output. Setting it in a rulebook YAML is a no-op at runtime.

    if effect.force_postmortem_mode is not None:
        mode = effect.force_postmortem_mode.strip().upper()
        state.postmortem_mode = None if mode in {"", "NONE"} else mode
    if effect.set_postmortem_required is not None:
        state.postmortem_required = effect.set_postmortem_required
        if not effect.set_postmortem_required:
            # Clear accumulated codes immediately when required=False; post-processing
            # in evaluate_rulebook_gates provides a second safety net but this makes
            # the invariant self-contained within _apply_gate_effect.
            state.postmortem_reason_codes.clear()
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
