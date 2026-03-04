"""Stage 6 gate-input assembly helpers."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, Environment
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput

GateScope = tuple[str, ...]
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
    proposed_action: Action = Action.OBSERVE
    diagnosis_confidence: float = 0.0
    partition_count_observed: int | None = None
    case_id: str | None = None
    decision_basis: Mapping[str, Any] | None = None


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
