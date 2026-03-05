"""Outbox state helpers for CaseFile durability sequencing."""

from __future__ import annotations

from datetime import UTC, datetime

from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, OutboxRecordV1


def create_ready_outbox_record(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Build a READY outbox record from confirmed-write casefile metadata."""
    resolved_now = now or datetime.now(tz=UTC)
    if resolved_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return OutboxRecordV1(
        case_id=confirmed_casefile.case_id,
        status="READY",
        casefile_object_path=confirmed_casefile.object_path,
        triage_hash=confirmed_casefile.triage_hash,
        created_at=resolved_now,
        updated_at=resolved_now,
        delivery_attempts=0,
    )


def mark_outbox_record_sent(
    *,
    record: OutboxRecordV1,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Transition a READY/RETRY outbox record to SENT after publish success."""
    if record.status not in {"READY", "RETRY"}:
        raise ValueError(f"cannot mark record SENT from status={record.status}")
    resolved_now = now or datetime.now(tz=UTC)
    if resolved_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return record.model_copy(
        update={
            "status": "SENT",
            "updated_at": resolved_now,
            "delivery_attempts": record.delivery_attempts + 1,
        }
    )
