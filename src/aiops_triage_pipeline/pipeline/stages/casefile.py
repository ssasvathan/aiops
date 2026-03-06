"""Stage 4.1 CaseFile triage assembly helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Mapping

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1
from aiops_triage_pipeline.contracts.prometheus_metrics import PrometheusMetricsContractV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.errors.exceptions import (
    CriticalDependencyError,
    IntegrationError,
    InvariantViolation,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileDiagnosisV1,
    CaseFileDownstreamImpact,
    CaseFileEvidenceRow,
    CaseFileEvidenceSnapshot,
    CaseFileLabelsV1,
    CaseFileLinkageV1,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.models.events import DegradedModeEvent
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1
from aiops_triage_pipeline.pipeline.stages.topology import TopologyStageOutput
from aiops_triage_pipeline.storage.casefile_io import (
    build_casefile_stage_object_key,
    build_casefile_triage_object_key,
    compute_casefile_diagnosis_hash,
    compute_casefile_labels_hash,
    compute_casefile_linkage_hash,
    compute_casefile_triage_hash,
    persist_casefile_diagnosis_write_once,
    persist_casefile_labels_write_once,
    persist_casefile_linkage_write_once,
    persist_casefile_triage_write_once,
    read_casefile_stage_json_or_none,
    serialize_casefile_triage,
    validate_casefile_triage_json,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol


def assemble_casefile_triage_stage(
    *,
    scope: tuple[str, ...],
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    topology_output: TopologyStageOutput,
    gate_input: GateInputV1,
    action_decision: ActionDecisionV1,
    rulebook_policy: RulebookV1,
    peak_policy: PeakPolicyV1,
    prometheus_metrics_contract: PrometheusMetricsContractV1,
    denylist: DenylistV1,
    diagnosis_policy_version: str,
    triage_timestamp: datetime | None = None,
    case_id: str | None = None,
) -> CaseFileTriageV1:
    """Assemble an immutable, denylist-sanitized CaseFile triage payload."""
    if gate_input.action_fingerprint != action_decision.action_fingerprint:
        raise ValueError("gate_input/action_decision action_fingerprint mismatch")

    resolved_scope = tuple(scope)
    if len(resolved_scope) not in (3, 4):
        raise ValueError(f"Unsupported scope shape for casefile assembly: {resolved_scope}")

    if not diagnosis_policy_version.strip():
        raise ValueError("diagnosis_policy_version must not be empty")

    resolved_timestamp = triage_timestamp or datetime.now(tz=UTC)
    if resolved_timestamp.tzinfo is None:
        raise ValueError("triage_timestamp must be timezone-aware")

    topology_context = _build_topology_context(
        scope=resolved_scope,
        topology_output=topology_output,
    )
    evidence_snapshot = _build_evidence_snapshot(
        scope=resolved_scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        gate_input=gate_input,
    )
    policy_versions = CaseFilePolicyVersions(
        rulebook_version=str(rulebook_policy.version),
        peak_policy_version=peak_policy.schema_version,
        prometheus_metrics_contract_version=prometheus_metrics_contract.version,
        exposure_denylist_version=denylist.denylist_version,
        diagnosis_policy_version=diagnosis_policy_version,
    )
    resolved_case_id = case_id or gate_input.case_id or _derive_case_id(gate_input=gate_input)

    casefile = CaseFileTriageV1(
        case_id=resolved_case_id,
        scope=resolved_scope,
        triage_timestamp=resolved_timestamp,
        evidence_snapshot=evidence_snapshot,
        topology_context=topology_context,
        gate_input=gate_input,
        action_decision=action_decision,
        policy_versions=policy_versions,
        triage_hash=TRIAGE_HASH_PLACEHOLDER,
    )
    sanitized_casefile = _sanitize_casefile(casefile=casefile, denylist=denylist)

    # Hash canonical bytes where triage_hash is replaced by a fixed placeholder.
    triage_hash = compute_casefile_triage_hash(sanitized_casefile)
    finalized = sanitized_casefile.model_copy(update={"triage_hash": triage_hash})

    # Enforce model_validate_json() round-trip at the boundary.
    return validate_casefile_triage_json(serialize_casefile_triage(finalized))


def _build_topology_context(
    *,
    scope: tuple[str, ...],
    topology_output: TopologyStageOutput,
) -> CaseFileTopologyContext:
    context = _resolve_scope_mapping(scope=scope, mapping=topology_output.context_by_scope)
    impact = _resolve_scope_mapping(scope=scope, mapping=topology_output.impact_by_scope)
    routing = _resolve_scope_mapping(scope=scope, mapping=topology_output.routing_by_scope)
    if context is None or impact is None or routing is None:
        raise KeyError(f"Missing topology context required for casefile scope={scope}")

    return CaseFileTopologyContext(
        stream_id=context.stream_id,
        topic_role=context.topic_role,
        criticality_tier=context.criticality_tier,
        source_system=context.source_system,
        blast_radius=impact.blast_radius,
        downstream_impacts=tuple(
            CaseFileDownstreamImpact(
                component_type=item.component_type,
                component_id=item.component_id,
                exposure_type=item.exposure_type,
                risk_status=item.risk_status,
            )
            for item in impact.downstream_impacts
        ),
        routing=CaseFileRoutingContext(
            lookup_level=routing.lookup_level,
            routing_key=routing.routing_key,
            owning_team_id=routing.owning_team_id,
            owning_team_name=routing.owning_team_name,
            support_channel=routing.support_channel,
            escalation_policy_ref=routing.escalation_policy_ref,
            service_now_assignment_group=routing.service_now_assignment_group,
        ),
    )


def _build_evidence_snapshot(
    *,
    scope: tuple[str, ...],
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    gate_input: GateInputV1,
) -> CaseFileEvidenceSnapshot:
    scoped_rows = tuple(
        CaseFileEvidenceRow(
            metric_key=row.metric_key,
            value=row.value,
            labels=dict(row.labels),
            scope=tuple(row.scope),
        )
        for row in evidence_output.rows
        if tuple(row.scope) == scope
    )
    status_map = dict(evidence_output.evidence_status_map_by_scope.get(scope, {}))
    if not status_map:
        status_map = dict(gate_input.evidence_status_map)

    peak_scope = (gate_input.env.value, gate_input.cluster_id, gate_input.topic)
    peak_context = peak_output.peak_context_by_scope.get(peak_scope)

    return CaseFileEvidenceSnapshot(
        scope=scope,
        rows=scoped_rows,
        evidence_status_map=status_map,
        telemetry_degraded_active=evidence_output.telemetry_degraded_active,
        max_safe_action=evidence_output.max_safe_action,
        peak_context=peak_context,
    )


def _resolve_scope_mapping(
    *,
    scope: tuple[str, ...],
    mapping: Mapping[tuple[str, ...], Any],
) -> Any | None:
    direct = mapping.get(scope)
    if direct is not None:
        return direct

    if len(scope) == 4:
        topic_scope = (scope[0], scope[1], scope[3])
        return mapping.get(topic_scope)
    return None


def _derive_case_id(*, gate_input: GateInputV1) -> str:
    digest_prefix = hashlib.sha256(gate_input.action_fingerprint.encode("utf-8")).hexdigest()[:12]
    return (
        f"case-{gate_input.env.value}-{gate_input.cluster_id}-"
        f"{gate_input.topic}-{digest_prefix}"
    )


def _sanitize_casefile(*, casefile: CaseFileTriageV1, denylist: DenylistV1) -> CaseFileTriageV1:
    payload = casefile.model_dump(mode="json")
    sanitized_payload = apply_denylist(payload, denylist)
    return CaseFileTriageV1.model_validate(sanitized_payload)


def persist_casefile_and_prepare_outbox_ready(
    *,
    casefile: CaseFileTriageV1,
    object_store_client: ObjectStoreClientProtocol,
) -> OutboxReadyCasefileV1:
    """Persist triage artifact and return a typed READY handoff payload."""
    logger = get_logger("pipeline.stages.casefile")
    object_path = build_casefile_triage_object_key(casefile.case_id)

    try:
        persisted = persist_casefile_triage_write_once(
            object_store_client=object_store_client,
            casefile=casefile,
        )
    except Exception as exc:
        if isinstance(exc, CriticalDependencyError):
            degraded_event = DegradedModeEvent(
                affected_scope="object_storage",
                reason=str(exc),
                capped_action_level="HALT",
                estimated_impact_window="unknown",
                timestamp=datetime.now(tz=UTC),
            )
            logger.critical(
                "casefile_persistence_halt_alert",
                event_type="DegradedModeEvent",
                case_id=casefile.case_id,
                object_path=object_path,
                affected_scope=degraded_event.affected_scope,
                reason=degraded_event.reason,
                capped_action_level=degraded_event.capped_action_level,
                estimated_impact_window=degraded_event.estimated_impact_window,
                timestamp=degraded_event.timestamp.isoformat(),
                error_type=type(exc).__name__,
            )
        else:
            logger.error(
                "casefile_persistence_failed",
                event_type="casefile.persistence_failed",
                case_id=casefile.case_id,
                object_path=object_path,
                reason=str(exc),
                error_type=type(exc).__name__,
            )
        raise

    logger.info(
        "casefile_persistence_confirmed",
        event_type="casefile.persistence_confirmed",
        case_id=persisted.case_id,
        object_path=persisted.object_path,
        triage_hash=persisted.triage_hash,
        write_result=persisted.write_result,
    )

    try:
        return OutboxReadyCasefileV1(
            case_id=persisted.case_id,
            object_path=persisted.object_path,
            triage_hash=persisted.triage_hash,
        )
    except Exception as exc:  # noqa: BLE001
        raise IntegrationError(
            "failed to construct outbox-ready payload from confirmed casefile persistence"
        ) from exc


def persist_casefile_diagnosis_stage(
    *,
    casefile: CaseFileDiagnosisV1,
    object_store_client: ObjectStoreClientProtocol,
) -> str:
    """Persist diagnosis.json as an append-only stage artifact with dependency checks."""
    _validate_diagnosis_stage_hashes(
        casefile=casefile,
        object_store_client=object_store_client,
    )
    persisted = persist_casefile_diagnosis_write_once(
        object_store_client=object_store_client,
        casefile=casefile,
    )
    return persisted.object_path


def persist_casefile_linkage_stage(
    *,
    casefile: CaseFileLinkageV1,
    object_store_client: ObjectStoreClientProtocol,
) -> str:
    """Persist linkage.json as an append-only stage artifact with dependency checks."""
    _validate_linkage_stage_hashes(
        casefile=casefile,
        object_store_client=object_store_client,
    )
    persisted = persist_casefile_linkage_write_once(
        object_store_client=object_store_client,
        casefile=casefile,
    )
    return persisted.object_path


def persist_casefile_labels_stage(
    *,
    casefile: CaseFileLabelsV1,
    object_store_client: ObjectStoreClientProtocol,
) -> str:
    """Persist labels.json as an append-only stage artifact with dependency checks."""
    _validate_labels_stage_hashes(
        casefile=casefile,
        object_store_client=object_store_client,
    )
    persisted = persist_casefile_labels_write_once(
        object_store_client=object_store_client,
        casefile=casefile,
    )
    return persisted.object_path


def load_casefile_diagnosis_stage_if_present(
    *,
    case_id: str,
    object_store_client: ObjectStoreClientProtocol,
) -> CaseFileDiagnosisV1 | None:
    """Load diagnosis.json and return explicit absence when stage was not written."""
    payload = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=case_id,
        stage="diagnosis",
    )
    if payload is None:
        _log_casefile_stage_absent(case_id=case_id, stage="diagnosis")
        return None
    return payload


def load_casefile_linkage_stage_if_present(
    *,
    case_id: str,
    object_store_client: ObjectStoreClientProtocol,
) -> CaseFileLinkageV1 | None:
    """Load linkage.json and return explicit absence when stage was not written."""
    payload = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=case_id,
        stage="linkage",
    )
    if payload is None:
        _log_casefile_stage_absent(case_id=case_id, stage="linkage")
        return None
    return payload


def load_casefile_labels_stage_if_present(
    *,
    case_id: str,
    object_store_client: ObjectStoreClientProtocol,
) -> CaseFileLabelsV1 | None:
    """Load labels.json and return explicit absence when stage was not written."""
    payload = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=case_id,
        stage="labels",
    )
    if payload is None:
        _log_casefile_stage_absent(case_id=case_id, stage="labels")
        return None
    return payload


def _validate_diagnosis_stage_hashes(
    *,
    casefile: CaseFileDiagnosisV1,
    object_store_client: ObjectStoreClientProtocol,
) -> None:
    expected_diagnosis_hash = compute_casefile_diagnosis_hash(casefile)
    if casefile.diagnosis_hash != expected_diagnosis_hash:
        raise InvariantViolation("diagnosis_hash mismatch before stage persistence")

    triage_payload = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="triage",
    )
    if triage_payload is None:
        raise InvariantViolation("diagnosis stage requires triage.json to exist")

    triage_hash = compute_casefile_triage_hash(triage_payload)
    if casefile.triage_hash != triage_hash:
        raise InvariantViolation(
            "diagnosis stage triage_hash mismatch (tamper or stale dependency)"
        )


def _validate_linkage_stage_hashes(
    *,
    casefile: CaseFileLinkageV1,
    object_store_client: ObjectStoreClientProtocol,
) -> None:
    expected_linkage_hash = compute_casefile_linkage_hash(casefile)
    if casefile.linkage_hash != expected_linkage_hash:
        raise InvariantViolation("linkage_hash mismatch before stage persistence")

    triage_payload = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="triage",
    )
    if triage_payload is None:
        raise InvariantViolation("linkage stage requires triage.json to exist")

    triage_hash = compute_casefile_triage_hash(triage_payload)
    if casefile.triage_hash != triage_hash:
        raise InvariantViolation("linkage stage triage_hash mismatch (tamper or stale dependency)")

    if casefile.diagnosis_hash is not None:
        diagnosis_payload = read_casefile_stage_json_or_none(
            object_store_client=object_store_client,
            case_id=casefile.case_id,
            stage="diagnosis",
        )
        if diagnosis_payload is None:
            raise InvariantViolation(
                "linkage stage diagnosis_hash was provided but diagnosis.json is absent"
            )
        diagnosis_hash = compute_casefile_diagnosis_hash(diagnosis_payload)
        if casefile.diagnosis_hash != diagnosis_hash:
            raise InvariantViolation("linkage stage diagnosis_hash mismatch")


def _validate_labels_stage_hashes(
    *,
    casefile: CaseFileLabelsV1,
    object_store_client: ObjectStoreClientProtocol,
) -> None:
    expected_labels_hash = compute_casefile_labels_hash(casefile)
    if casefile.labels_hash != expected_labels_hash:
        raise InvariantViolation("labels_hash mismatch before stage persistence")

    triage_payload = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="triage",
    )
    if triage_payload is None:
        raise InvariantViolation("labels stage requires triage.json to exist")

    triage_hash = compute_casefile_triage_hash(triage_payload)
    if casefile.triage_hash != triage_hash:
        raise InvariantViolation("labels stage triage_hash mismatch (tamper or stale dependency)")

    if casefile.diagnosis_hash is not None:
        diagnosis_payload = read_casefile_stage_json_or_none(
            object_store_client=object_store_client,
            case_id=casefile.case_id,
            stage="diagnosis",
        )
        if diagnosis_payload is None:
            raise InvariantViolation(
                "labels stage diagnosis_hash was provided but diagnosis.json is absent"
            )
        diagnosis_hash = compute_casefile_diagnosis_hash(diagnosis_payload)
        if casefile.diagnosis_hash != diagnosis_hash:
            raise InvariantViolation("labels stage diagnosis_hash mismatch")


def _log_casefile_stage_absent(*, case_id: str, stage: str) -> None:
    logger = get_logger("pipeline.stages.casefile")
    object_path = build_casefile_stage_object_key(case_id=case_id, stage=stage)
    logger.info(
        "casefile_stage_absent",
        event_type="casefile.stage_absent",
        case_id=case_id,
        stage=stage,
        object_path=object_path,
    )
