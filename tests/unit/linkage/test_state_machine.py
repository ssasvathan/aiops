from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiops_triage_pipeline.linkage.state_machine import (
    create_pending_linkage_retry_record,
    is_retry_due,
    mark_linkage_failure,
    mark_linkage_searching,
    mark_linkage_success,
)
from aiops_triage_pipeline.outbox.state_machine import compute_retry_delay_seconds


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


def test_mark_linkage_failure_exponential_backoff_progresses_per_attempt() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base)
    first_failure = mark_linkage_failure(
        record=searching,
        transient=True,
        error_code="timeout",
        error_message="timed out",
        request_id="req-exp-1",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.0,
        now=base,
    )
    second_searching = mark_linkage_searching(
        record=first_failure,
        now=first_failure.next_attempt_at or (base + timedelta(seconds=30)),
    )
    second_failure = mark_linkage_failure(
        record=second_searching,
        transient=True,
        error_code="timeout",
        error_message="timed out",
        request_id="req-exp-2",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.0,
        now=second_searching.updated_at,
    )

    assert first_failure.next_attempt_at is not None
    assert second_failure.next_attempt_at is not None
    first_delay = int((first_failure.next_attempt_at - first_failure.updated_at).total_seconds())
    second_delay = int((second_failure.next_attempt_at - second_failure.updated_at).total_seconds())
    expected_first = compute_retry_delay_seconds(
        case_id=first_failure.case_id,
        attempt_number=1,
        base_seconds=30,
        max_seconds=900,
        jitter_ratio=0.0,
    )
    expected_second = compute_retry_delay_seconds(
        case_id=second_failure.case_id,
        attempt_number=2,
        base_seconds=30,
        max_seconds=900,
        jitter_ratio=0.0,
    )
    assert first_delay == expected_first
    assert second_delay == expected_second
    assert second_delay > first_delay


def test_mark_linkage_failure_jitter_is_bounded_for_attempt() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base)
    failed_temp = mark_linkage_failure(
        record=searching,
        transient=True,
        error_code="http_5xx",
        error_message="http_status=503",
        request_id="req-jitter",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=base,
    )

    assert failed_temp.next_attempt_at is not None
    scheduled_delay = int((failed_temp.next_attempt_at - failed_temp.updated_at).total_seconds())
    expected_delay = compute_retry_delay_seconds(
        case_id=failed_temp.case_id,
        attempt_number=1,
        base_seconds=30,
        max_seconds=900,
        jitter_ratio=0.2,
    )
    assert scheduled_delay == expected_delay
    assert 24 <= scheduled_delay <= 36


def test_mark_linkage_failure_retry_after_is_bounded_by_retry_max_seconds() -> None:
    base, record = _pending_record()
    searching = mark_linkage_searching(record=record, now=base)
    failed_temp = mark_linkage_failure(
        record=searching,
        transient=True,
        error_code="http_429",
        error_message="http_status=429",
        request_id="req-retry-after",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        retry_after_seconds=9_999,
        now=base,
    )

    assert failed_temp.next_attempt_at is not None
    assert failed_temp.last_retry_after_seconds == 900
    scheduled_delay = int((failed_temp.next_attempt_at - failed_temp.updated_at).total_seconds())
    assert scheduled_delay == 900
