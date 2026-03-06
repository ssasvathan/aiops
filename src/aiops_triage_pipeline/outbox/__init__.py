"""Outbox contracts and helpers."""

from aiops_triage_pipeline.outbox.publisher import (
    CaseEventPublisherProtocol,
    CaseEventsPublishEvidenceV1,
    CaseHeaderPublisherProtocol,
    HeaderPublishEvidenceV1,
    build_outbox_case_events,
    publish_case_events_after_invariant_a,
    publish_case_header_after_invariant_a,
)
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import (
    OUTBOX_STATES,
    OutboxReadyCasefileV1,
    OutboxRecordV1,
    create_outbox_table,
    outbox_table,
)
from aiops_triage_pipeline.outbox.state_machine import (
    create_pending_outbox_record,
    create_ready_outbox_record,
    mark_outbox_record_publish_failure,
    mark_outbox_record_ready,
    mark_outbox_record_sent,
    retention_cutoff_for_state,
)
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker

__all__ = [
    "OUTBOX_STATES",
    "CaseEventPublisherProtocol",
    "CaseEventsPublishEvidenceV1",
    "CaseHeaderPublisherProtocol",
    "HeaderPublishEvidenceV1",
    "OutboxPublisherWorker",
    "OutboxSqlRepository",
    "OutboxReadyCasefileV1",
    "OutboxRecordV1",
    "create_outbox_table",
    "outbox_table",
    "build_outbox_case_events",
    "create_pending_outbox_record",
    "create_ready_outbox_record",
    "mark_outbox_record_publish_failure",
    "mark_outbox_record_ready",
    "mark_outbox_record_sent",
    "publish_case_events_after_invariant_a",
    "publish_case_header_after_invariant_a",
    "retention_cutoff_for_state",
]
