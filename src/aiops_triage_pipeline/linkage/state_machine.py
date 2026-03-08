"""ServiceNow linkage retry state transitions with deterministic scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.linkage.schema import LinkageRetryRecordV1
from aiops_triage_pipeline.outbox.state_machine import compute_retry_delay_seconds


def create_pending_linkage_retry_record(
    *,
    case_id: str,
    pd_incident_id: str,
    incident_sys_id: str | None,
    retry_window_minutes: int,
    now: datetime | None = None,
) -> LinkageRetryRecordV1:
    """Initialize linkage retry state for a case."""
    resolved_now = _resolve_now(now=now)
    return LinkageRetryRecordV1(
        case_id=case_id,
        pd_incident_id=pd_incident_id,
        incident_sys_id=incident_sys_id,
        state="PENDING",
        attempt_count=0,
        retry_window_minutes=retry_window_minutes,
        first_attempt_at=resolved_now,
        updated_at=resolved_now,
        deadline_at=resolved_now + timedelta(minutes=retry_window_minutes),
        next_attempt_at=None,
        request_id=None,
        last_error_code=None,
        last_error_message=None,
        last_retry_after_seconds=None,
        last_reason_metadata={},
    )


def is_retry_due(*, record: LinkageRetryRecordV1, now: datetime | None = None) -> bool:
    """Return True when a linkage record should run an attempt now."""
    resolved_now = _resolve_now(now=now)
    if record.state == "FAILED_TEMP":
        return record.next_attempt_at is None or record.next_attempt_at <= resolved_now
    return record.state in {"PENDING", "SEARCHING"}


def mark_linkage_searching(
    *,
    record: LinkageRetryRecordV1,
    now: datetime | None = None,
) -> LinkageRetryRecordV1:
    """Transition PENDING/FAILED_TEMP to SEARCHING before a linkage attempt."""
    if record.state in {"LINKED", "FAILED_FINAL"}:
        raise InvariantViolation(f"cannot enter SEARCHING from state={record.state}")
    resolved_now = _resolve_transition_now(record=record, now=now)
    return record.model_copy(
        update={
            "state": "SEARCHING",
            "updated_at": resolved_now,
            "next_attempt_at": None,
        }
    )


def mark_linkage_success(
    *,
    record: LinkageRetryRecordV1,
    request_id: str | None,
    incident_sys_id: str | None,
    now: datetime | None = None,
) -> LinkageRetryRecordV1:
    """Transition SEARCHING to LINKED on successful linkage."""
    if record.state != "SEARCHING":
        raise InvariantViolation(f"cannot mark linkage success from state={record.state}")
    resolved_now = _resolve_transition_now(record=record, now=now)
    return record.model_copy(
        update={
            "state": "LINKED",
            "attempt_count": record.attempt_count + 1,
            "updated_at": resolved_now,
            "incident_sys_id": incident_sys_id or record.incident_sys_id,
            "request_id": request_id,
            "next_attempt_at": None,
            "last_error_code": None,
            "last_error_message": None,
            "last_retry_after_seconds": None,
            "last_reason_metadata": {},
        }
    )


def mark_linkage_failure(
    *,
    record: LinkageRetryRecordV1,
    transient: bool,
    error_code: str,
    error_message: str,
    request_id: str | None,
    retry_base_seconds: int,
    retry_max_seconds: int,
    retry_jitter_ratio: float,
    retry_after_seconds: int | None = None,
    reason_metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> LinkageRetryRecordV1:
    """Transition SEARCHING to FAILED_TEMP or FAILED_FINAL based on retry policy and deadline."""
    if record.state != "SEARCHING":
        raise InvariantViolation(f"cannot mark linkage failure from state={record.state}")
    resolved_now = _resolve_transition_now(record=record, now=now)
    next_attempt_number = record.attempt_count + 1
    metadata = dict(reason_metadata or {})

    if not transient:
        return record.model_copy(
            update={
                "state": "FAILED_FINAL",
                "attempt_count": next_attempt_number,
                "updated_at": resolved_now,
                "request_id": request_id,
                "next_attempt_at": None,
                "last_error_code": error_code,
                "last_error_message": error_message,
                "last_retry_after_seconds": retry_after_seconds,
                "last_reason_metadata": metadata,
            }
        )

    if resolved_now >= record.deadline_at:
        metadata["source_error_code"] = error_code
        return record.model_copy(
            update={
                "state": "FAILED_FINAL",
                "attempt_count": next_attempt_number,
                "updated_at": resolved_now,
                "request_id": request_id,
                "next_attempt_at": None,
                "last_error_code": "retry_window_exhausted",
                "last_error_message": "retry window exhausted before scheduling next attempt",
                "last_retry_after_seconds": retry_after_seconds,
                "last_reason_metadata": metadata,
            }
        )

    retry_delay_seconds = compute_retry_delay_seconds(
        case_id=record.case_id,
        attempt_number=next_attempt_number,
        base_seconds=retry_base_seconds,
        max_seconds=retry_max_seconds,
        jitter_ratio=retry_jitter_ratio,
    )
    bounded_retry_after = None
    if retry_after_seconds is not None and retry_after_seconds > 0:
        bounded_retry_after = min(retry_after_seconds, retry_max_seconds)
        retry_delay_seconds = max(retry_delay_seconds, bounded_retry_after)
    next_attempt_at = resolved_now + timedelta(seconds=retry_delay_seconds)

    if next_attempt_at > record.deadline_at:
        metadata["source_error_code"] = error_code
        metadata["source_retry_delay_seconds"] = retry_delay_seconds
        return record.model_copy(
            update={
                "state": "FAILED_FINAL",
                "attempt_count": next_attempt_number,
                "updated_at": resolved_now,
                "request_id": request_id,
                "next_attempt_at": None,
                "last_error_code": "retry_window_exhausted",
                "last_error_message": "retry window exhausted before scheduling next attempt",
                "last_retry_after_seconds": bounded_retry_after,
                "last_reason_metadata": metadata,
            }
        )

    return record.model_copy(
        update={
            "state": "FAILED_TEMP",
            "attempt_count": next_attempt_number,
            "updated_at": resolved_now,
            "request_id": request_id,
            "next_attempt_at": next_attempt_at,
            "last_error_code": error_code,
            "last_error_message": error_message,
            "last_retry_after_seconds": bounded_retry_after,
            "last_reason_metadata": metadata,
        }
    )


def _resolve_now(*, now: datetime | None) -> datetime:
    resolved_now = now or datetime.now(tz=UTC)
    if resolved_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return resolved_now


def _resolve_transition_now(*, record: LinkageRetryRecordV1, now: datetime | None) -> datetime:
    """Ensure linkage transition timestamps never move backward."""
    resolved_now = _resolve_now(now=now)
    if resolved_now < record.updated_at:
        return record.updated_at
    return resolved_now
