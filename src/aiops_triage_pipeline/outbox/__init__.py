"""Outbox contracts and helpers."""

from aiops_triage_pipeline.outbox.publisher import (
    CaseHeaderPublisherProtocol,
    HeaderPublishEvidenceV1,
    publish_case_header_after_invariant_a,
)
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, OutboxRecordV1
from aiops_triage_pipeline.outbox.state_machine import (
    create_ready_outbox_record,
    mark_outbox_record_sent,
)

__all__ = [
    "CaseHeaderPublisherProtocol",
    "HeaderPublishEvidenceV1",
    "OutboxReadyCasefileV1",
    "OutboxRecordV1",
    "create_ready_outbox_record",
    "mark_outbox_record_sent",
    "publish_case_header_after_invariant_a",
]
