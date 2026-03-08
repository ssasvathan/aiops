from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiops_triage_pipeline.linkage.state_machine import (
    create_pending_linkage_retry_record,
    is_retry_due,
    mark_linkage_failure,
    mark_linkage_searching,
    mark_linkage_success,
)


def _pending_record() -> tuple[datetime, object]:
    base = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    record = create_pending_linkage_retry_record(
        case_id="case-sn-001",
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        retry_window_minutes=120,
        now=base,
    )
    return base, record


def test_create_pending_linkage_retry_record_initializes_window() -> None:
    base, record = _pending_record()

    assert record.state == "PENDING"
    assert record.attempt_count == 0
    assert record.first_attempt_at == base
    assert record.deadline_at == base + timedelta(minutes=120)
    assert record.next_attempt_at is None


def test_mark_linkage_success_transitions_searching_to_linked() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base + timedelta(seconds=1))
    linked = mark_linkage_success(
        record=searching,
        request_id="req-1",
        incident_sys_id="inc-001",
        now=base + timedelta(seconds=2),
    )

    assert linked.state == "LINKED"
    assert linked.attempt_count == 1
    assert linked.request_id == "req-1"
    assert linked.next_attempt_at is None


def test_mark_linkage_failure_transient_schedules_failed_temp_retry() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base)
    failed_temp = mark_linkage_failure(
        record=searching,
        transient=True,
        error_code="http_503",
        error_message="http_status=503",
        request_id="req-2",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=base + timedelta(seconds=5),
    )

    assert failed_temp.state == "FAILED_TEMP"
    assert failed_temp.attempt_count == 1
    assert failed_temp.next_attempt_at is not None
    assert failed_temp.next_attempt_at > failed_temp.updated_at
    assert failed_temp.last_error_code == "http_503"


def test_mark_linkage_failure_transient_expired_window_becomes_failed_final() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base + timedelta(minutes=121))
    failed_final = mark_linkage_failure(
        record=searching,
        transient=True,
        error_code="http_5xx",
        error_message="http_status=503",
        request_id="req-3",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=base + timedelta(minutes=121),
    )

    assert failed_final.state == "FAILED_FINAL"
    assert failed_final.last_error_code == "retry_window_exhausted"


def test_mark_linkage_failure_non_transient_is_terminal_failed_final() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base)
    failed_final = mark_linkage_failure(
        record=searching,
        transient=False,
        error_code="invalid_input",
        error_message="missing_incident_sys_id",
        request_id="req-4",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=base + timedelta(seconds=3),
    )

    assert failed_final.state == "FAILED_FINAL"
    assert failed_final.attempt_count == 1
    assert failed_final.next_attempt_at is None
    assert failed_final.last_error_code == "invalid_input"


def test_is_retry_due_checks_next_attempt_timestamp() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base)
    failed_temp = mark_linkage_failure(
        record=searching,
        transient=True,
        error_code="timeout",
        error_message="timed out",
        request_id="req-5",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=base,
    )

    assert failed_temp.next_attempt_at is not None
    assert is_retry_due(record=failed_temp, now=base) is False
    assert is_retry_due(record=failed_temp, now=failed_temp.next_attempt_at) is True
