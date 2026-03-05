"""Stage helpers for outbox READY-transition guardrails."""

from __future__ import annotations

from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.outbox.publisher import (
    CaseHeaderPublisherProtocol,
    HeaderPublishEvidenceV1,
    publish_case_header_after_invariant_a,
)
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, OutboxRecordV1
from aiops_triage_pipeline.outbox.state_machine import create_ready_outbox_record
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol


def build_outbox_ready_record(*, confirmed_casefile: OutboxReadyCasefileV1) -> OutboxRecordV1:
    """Build typed outbox READY record from confirmed-write casefile metadata."""
    return create_ready_outbox_record(confirmed_casefile=confirmed_casefile)


def build_outbox_ready_transition_payload(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
) -> dict[str, str]:
    """Build minimal READY-transition payload from confirmed casefile metadata."""
    outbox_record = build_outbox_ready_record(confirmed_casefile=confirmed_casefile)
    return {
        "status": outbox_record.status,
        "case_id": outbox_record.case_id,
        "casefile_object_path": outbox_record.casefile_object_path,
        "triage_hash": outbox_record.triage_hash,
    }


def publish_case_header_after_confirmed_casefile(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    case_header_event: CaseHeaderEventV1,
    object_store_client: ObjectStoreClientProtocol,
    publisher: CaseHeaderPublisherProtocol,
) -> HeaderPublishEvidenceV1:
    """Enforce Invariant A before publishing a case header from READY metadata."""
    outbox_record = build_outbox_ready_record(confirmed_casefile=confirmed_casefile)
    return publish_case_header_after_invariant_a(
        outbox_record=outbox_record,
        case_header_event=case_header_event,
        object_store_client=object_store_client,
        publisher=publisher,
    )
