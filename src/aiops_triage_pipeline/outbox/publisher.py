"""Outbox publish helpers that enforce Invariant A before Kafka emission."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from pydantic import AwareDatetime, BaseModel, ValidationError

from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.enforcement import apply_denylist_with_removed_count
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.errors.exceptions import (
    CriticalDependencyError,
    DenylistSanitizationError,
    InvariantViolation,
    PublishAfterDenylistError,
)
from aiops_triage_pipeline.models.case_file import CaseFileTriageV1
from aiops_triage_pipeline.outbox.schema import OutboxRecordV1
from aiops_triage_pipeline.storage.casefile_io import validate_casefile_triage_json
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

_TRIAGE_EXCERPT_PUBLISH_BOUNDARY_ID = "outbox.triage_excerpt.kafka_publish"


class CaseHeaderPublisherProtocol(Protocol):
    """Abstraction for publishing CaseHeaderEvent to Kafka (or test doubles)."""

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None: ...


class CaseEventPublisherProtocol(Protocol):
    """Abstraction for publishing both outbox events as one durable action."""

    def publish_case_events(
        self,
        *,
        case_header_event: CaseHeaderEventV1,
        triage_excerpt_event: TriageExcerptV1,
    ) -> None: ...


class HeaderPublishEvidenceV1(BaseModel, frozen=True):
    """Evidence that header publication occurred after a confirmed CaseFile read."""

    case_id: str
    casefile_object_path: str
    triage_hash: str
    published_at: AwareDatetime


class CaseEventsPublishEvidenceV1(BaseModel, frozen=True):
    """Evidence that dual-event publication occurred after confirmed CaseFile readback."""

    case_id: str
    casefile_object_path: str
    triage_hash: str
    env: str
    topic: str
    anomaly_family: str
    final_action: str
    published_at: AwareDatetime
    event_count: int = 2
    boundary_id: str = _TRIAGE_EXCERPT_PUBLISH_BOUNDARY_ID
    removed_field_count: int = 0


def publish_case_header_after_invariant_a(
    *,
    outbox_record: OutboxRecordV1,
    case_header_event: CaseHeaderEventV1,
    object_store_client: ObjectStoreClientProtocol,
    publisher: CaseHeaderPublisherProtocol,
    published_at: datetime | None = None,
) -> HeaderPublishEvidenceV1:
    """Publish a case header only after object-store readback confirms persisted triage artifact."""
    if outbox_record.status != "READY":
        raise InvariantViolation(
            f"cannot publish case header from outbox status={outbox_record.status}; expected READY"
        )
    if case_header_event.case_id != outbox_record.case_id:
        raise InvariantViolation("case_header_event.case_id does not match outbox record case_id")

    _readback_casefile_for_outbox_record(
        outbox_record=outbox_record,
        object_store_client=object_store_client,
    )

    publisher.publish_case_header(event=case_header_event)
    resolved_published_at = published_at or datetime.now(tz=UTC)
    if resolved_published_at.tzinfo is None:
        raise ValueError("published_at must be timezone-aware")
    return HeaderPublishEvidenceV1(
        case_id=outbox_record.case_id,
        casefile_object_path=outbox_record.casefile_object_path,
        triage_hash=outbox_record.triage_hash,
        published_at=resolved_published_at,
    )


def publish_case_events_after_invariant_a(
    *,
    outbox_record: OutboxRecordV1,
    object_store_client: ObjectStoreClientProtocol,
    publisher: CaseEventPublisherProtocol,
    denylist: DenylistV1,
    published_at: datetime | None = None,
) -> CaseEventsPublishEvidenceV1:
    """Publish header + excerpt after object-store readback confirms persisted triage artifact."""
    if outbox_record.status not in {"READY", "RETRY"}:
        raise InvariantViolation(
            f"cannot publish case events from outbox status={outbox_record.status}; "
            "expected READY or RETRY"
        )

    persisted_casefile = _readback_casefile_for_outbox_record(
        outbox_record=outbox_record,
        object_store_client=object_store_client,
    )
    case_header_event, triage_excerpt_event = build_outbox_case_events(casefile=persisted_casefile)
    sanitization_result = sanitize_triage_excerpt_for_publish(
        triage_excerpt=triage_excerpt_event,
        denylist=denylist,
    )
    try:
        publisher.publish_case_events(
            case_header_event=case_header_event,
            triage_excerpt_event=sanitization_result.triage_excerpt,
        )
    except Exception as exc:  # noqa: BLE001
        raise PublishAfterDenylistError(
            "case events publish failed after denylist sanitization",
            boundary_id=_TRIAGE_EXCERPT_PUBLISH_BOUNDARY_ID,
            removed_field_count=sanitization_result.removed_field_count,
            error_code=type(exc).__name__,
        ) from exc

    resolved_published_at = published_at or datetime.now(tz=UTC)
    if resolved_published_at.tzinfo is None:
        raise ValueError("published_at must be timezone-aware")
    return CaseEventsPublishEvidenceV1(
        case_id=outbox_record.case_id,
        casefile_object_path=outbox_record.casefile_object_path,
        triage_hash=outbox_record.triage_hash,
        env=case_header_event.env.value,
        topic=case_header_event.topic,
        anomaly_family=case_header_event.anomaly_family,
        final_action=case_header_event.final_action.value,
        published_at=resolved_published_at,
        removed_field_count=sanitization_result.removed_field_count,
    )


def build_outbox_case_events(
    *,
    casefile: CaseFileTriageV1,
) -> tuple[CaseHeaderEventV1, TriageExcerptV1]:
    """Build CaseHeaderEvent.v1 and TriageExcerpt.v1 from persisted triage.json."""
    case_header = CaseHeaderEventV1(
        case_id=casefile.case_id,
        env=casefile.gate_input.env,
        cluster_id=casefile.gate_input.cluster_id,
        stream_id=casefile.gate_input.stream_id,
        topic=casefile.gate_input.topic,
        anomaly_family=casefile.gate_input.anomaly_family,
        criticality_tier=casefile.topology_context.criticality_tier,
        final_action=casefile.action_decision.final_action,
        routing_key=casefile.topology_context.routing.routing_key,
        evaluation_ts=casefile.triage_timestamp,
    )
    triage_excerpt = TriageExcerptV1(
        case_id=casefile.case_id,
        env=casefile.gate_input.env,
        cluster_id=casefile.gate_input.cluster_id,
        stream_id=casefile.gate_input.stream_id,
        topic=casefile.gate_input.topic,
        anomaly_family=casefile.gate_input.anomaly_family,
        topic_role=casefile.topology_context.topic_role,
        criticality_tier=casefile.topology_context.criticality_tier,
        routing_key=casefile.topology_context.routing.routing_key,
        sustained=casefile.gate_input.sustained,
        peak=casefile.gate_input.peak,
        evidence_status_map=dict(casefile.evidence_snapshot.evidence_status_map),
        findings=tuple(casefile.gate_input.findings),
        triage_timestamp=casefile.triage_timestamp,
    )
    return case_header, triage_excerpt


class SanitizedTriageExcerptV1(BaseModel, frozen=True):
    """Result bundle for denylist-enforced triage excerpt payloads."""

    triage_excerpt: TriageExcerptV1
    removed_field_count: int


def sanitize_triage_excerpt_for_publish(
    *,
    triage_excerpt: TriageExcerptV1,
    denylist: DenylistV1,
) -> SanitizedTriageExcerptV1:
    """Apply shared denylist enforcement and re-validate TriageExcerpt contract."""
    sanitized_payload, removed_field_count = apply_denylist_with_removed_count(
        triage_excerpt.model_dump(mode="json"),
        denylist,
    )
    try:
        sanitized_excerpt = TriageExcerptV1.model_validate(sanitized_payload)
    except ValidationError as exc:
        raise DenylistSanitizationError(
            "triage excerpt denylist sanitization produced schema-invalid payload",
            boundary_id=_TRIAGE_EXCERPT_PUBLISH_BOUNDARY_ID,
            removed_field_count=removed_field_count,
        ) from exc

    return SanitizedTriageExcerptV1(
        triage_excerpt=sanitized_excerpt,
        removed_field_count=removed_field_count,
    )


def _readback_casefile_for_outbox_record(
    *,
    outbox_record: OutboxRecordV1,
    object_store_client: ObjectStoreClientProtocol,
) -> CaseFileTriageV1:
    try:
        payload = object_store_client.get_object_bytes(key=outbox_record.casefile_object_path)
    except CriticalDependencyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InvariantViolation(
            "cannot publish case events before casefile object is readable from storage"
        ) from exc

    try:
        persisted_casefile = validate_casefile_triage_json(payload)
    except Exception as exc:  # noqa: BLE001
        raise InvariantViolation(
            "cannot publish case events because persisted casefile payload failed hash validation"
        ) from exc

    if persisted_casefile.case_id != outbox_record.case_id:
        raise InvariantViolation("persisted casefile case_id does not match outbox record")
    if persisted_casefile.triage_hash != outbox_record.triage_hash:
        raise InvariantViolation("persisted casefile triage_hash does not match outbox record")
    return persisted_casefile
