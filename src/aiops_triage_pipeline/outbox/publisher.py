"""Outbox publish helpers that enforce Invariant A before header emission."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from pydantic import AwareDatetime, BaseModel

from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError, InvariantViolation
from aiops_triage_pipeline.outbox.schema import OutboxRecordV1
from aiops_triage_pipeline.storage.casefile_io import validate_casefile_triage_json
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol


class CaseHeaderPublisherProtocol(Protocol):
    """Abstraction for publishing CaseHeaderEvent to Kafka (or test doubles)."""

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None: ...


class HeaderPublishEvidenceV1(BaseModel, frozen=True):
    """Evidence that header publication occurred after a confirmed CaseFile read."""

    case_id: str
    casefile_object_path: str
    triage_hash: str
    published_at: AwareDatetime


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

    try:
        payload = object_store_client.get_object_bytes(key=outbox_record.casefile_object_path)
    except CriticalDependencyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InvariantViolation(
            "cannot publish case header before casefile object is readable from storage"
        ) from exc

    try:
        persisted_casefile = validate_casefile_triage_json(payload)
    except Exception as exc:  # noqa: BLE001
        raise InvariantViolation(
            "cannot publish case header because persisted casefile payload failed hash validation"
        ) from exc

    if persisted_casefile.case_id != outbox_record.case_id:
        raise InvariantViolation("persisted casefile case_id does not match outbox record")
    if persisted_casefile.triage_hash != outbox_record.triage_hash:
        raise InvariantViolation("persisted casefile triage_hash does not match outbox record")

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
