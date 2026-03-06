"""Outbox state helpers for CaseFile durability sequencing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, OutboxRecordV1


def create_pending_outbox_record(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Build a PENDING_OBJECT outbox record from confirmed-write casefile metadata."""
    resolved_now = _resolve_now(now=now)
    return OutboxRecordV1(
        case_id=confirmed_casefile.case_id,
        status="PENDING_OBJECT",
        casefile_object_path=confirmed_casefile.object_path,
        triage_hash=confirmed_casefile.triage_hash,
        created_at=resolved_now,
        updated_at=resolved_now,
        delivery_attempts=0,
        next_attempt_at=None,
        last_error_code=None,
        last_error_message=None,
    )


def create_ready_outbox_record(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Build a READY outbox record from confirmed-write casefile metadata."""
    resolved_now = _resolve_now(now=now)
    return OutboxRecordV1(
        case_id=confirmed_casefile.case_id,
        status="READY",
        casefile_object_path=confirmed_casefile.object_path,
        triage_hash=confirmed_casefile.triage_hash,
        created_at=resolved_now,
        updated_at=resolved_now,
        delivery_attempts=0,
        next_attempt_at=None,
        last_error_code=None,
        last_error_message=None,
    )


def mark_outbox_record_ready(
    *,
    record: OutboxRecordV1,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Transition a PENDING_OBJECT outbox record to READY after write confirmation."""
    if record.status != "PENDING_OBJECT":
        raise InvariantViolation(f"cannot mark record READY from status={record.status}")
    resolved_now = _resolve_transition_now(record=record, now=now)
    return record.model_copy(
        update={
            "status": "READY",
            "updated_at": resolved_now,
            "next_attempt_at": None,
            "last_error_code": None,
            "last_error_message": None,
        }
    )


def mark_outbox_record_sent(
    *,
    record: OutboxRecordV1,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Transition a READY/RETRY outbox record to SENT after publish success."""
    if record.status not in {"READY", "RETRY"}:
        raise InvariantViolation(f"cannot mark record SENT from status={record.status}")
    resolved_now = _resolve_transition_now(record=record, now=now)
    return record.model_copy(
        update={
            "status": "SENT",
            "updated_at": resolved_now,
            "delivery_attempts": record.delivery_attempts + 1,
            "next_attempt_at": None,
            "last_error_code": None,
            "last_error_message": None,
        }
    )


def mark_outbox_record_publish_failure(
    *,
    record: OutboxRecordV1,
    policy: OutboxPolicyV1,
    app_env: str,
    error_message: str,
    error_code: str | None = None,
    now: datetime | None = None,
) -> OutboxRecordV1:
    """Transition READY/RETRY to RETRY, or RETRY to DEAD when attempts exceed policy threshold."""
    if record.status not in {"READY", "RETRY"}:
        raise InvariantViolation(f"cannot mark publish failure from status={record.status}")
    resolved_now = _resolve_transition_now(record=record, now=now)
    next_attempt_number = record.delivery_attempts + 1
    max_retry_attempts = resolve_max_retry_attempts(policy=policy, app_env=app_env)
    if next_attempt_number > max_retry_attempts:
        return record.model_copy(
            update={
                "status": "DEAD",
                "updated_at": resolved_now,
                "delivery_attempts": next_attempt_number,
                "next_attempt_at": None,
                "last_error_code": error_code,
                "last_error_message": error_message,
            }
        )

    retry_delay_seconds = compute_retry_delay_seconds(
        case_id=record.case_id,
        attempt_number=next_attempt_number,
    )
    return record.model_copy(
        update={
            "status": "RETRY",
            "updated_at": resolved_now,
            "delivery_attempts": next_attempt_number,
            "next_attempt_at": resolved_now + timedelta(seconds=retry_delay_seconds),
            "last_error_code": error_code,
            "last_error_message": error_message,
        }
    )


def compute_retry_delay_seconds(
    *,
    case_id: str,
    attempt_number: int,
    base_seconds: int = 30,
    max_seconds: int = 900,
    jitter_ratio: float = 0.2,
) -> int:
    """Compute deterministic exponential backoff with bounded jitter for testable retries."""
    if attempt_number <= 0:
        raise ValueError("attempt_number must be >= 1")
    exp_seconds = min(base_seconds * (2 ** (attempt_number - 1)), max_seconds)
    jitter_window = max(1, int(exp_seconds * jitter_ratio))
    digest = sha256(f"{case_id}:{attempt_number}".encode("utf-8")).digest()
    jitter_value = int.from_bytes(digest[:4], "big") % ((2 * jitter_window) + 1)
    signed_jitter = jitter_value - jitter_window
    return max(1, exp_seconds + signed_jitter)


def resolve_max_retry_attempts(*, policy: OutboxPolicyV1, app_env: str) -> int:
    """Resolve max retry attempts from outbox-policy-v1 using APP_ENV."""
    try:
        return policy.retention_by_env[app_env].max_retry_attempts
    except KeyError as exc:
        raise ValueError(f"unsupported app_env for outbox retry policy: {app_env}") from exc


def retention_cutoff_for_state(
    *,
    policy: OutboxPolicyV1,
    app_env: str,
    state: str,
    now: datetime | None = None,
) -> datetime | None:
    """Return retention cutoff for SENT/DEAD rows; unresolved states have no cutoff."""
    resolved_now = _resolve_now(now=now)
    retention = policy.retention_by_env.get(app_env)
    if retention is None:
        raise ValueError(f"unsupported app_env for outbox retention policy: {app_env}")
    if state == "SENT":
        return resolved_now - timedelta(days=retention.sent_retention_days)
    if state == "DEAD":
        return resolved_now - timedelta(days=retention.dead_retention_days)
    return None


def _resolve_now(*, now: datetime | None) -> datetime:
    resolved_now = now or datetime.now(tz=UTC)
    if resolved_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return resolved_now


def _resolve_transition_now(*, record: OutboxRecordV1, now: datetime | None) -> datetime:
    """Ensure transition timestamps never move backward relative to stored record state."""
    resolved_now = _resolve_now(now=now)
    if resolved_now < record.updated_at:
        return record.updated_at
    return resolved_now
