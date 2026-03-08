from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine

from aiops_triage_pipeline.linkage.repository import ServiceNowLinkageRetrySqlRepository
from aiops_triage_pipeline.linkage.state_machine import (
    mark_linkage_failure,
    mark_linkage_searching,
    mark_linkage_success,
)


def test_get_or_create_pending_is_idempotent_for_same_case() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    repository = ServiceNowLinkageRetrySqlRepository(engine=engine)
    repository.ensure_schema()
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    first = repository.get_or_create_pending(
        case_id="case-sn-001",
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        retry_window_minutes=120,
        now=now,
    )
    second = repository.get_or_create_pending(
        case_id="case-sn-001",
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        retry_window_minutes=120,
        now=now + timedelta(minutes=1),
    )

    assert first.case_id == second.case_id
    assert second.first_attempt_at == first.first_attempt_at
    assert second.state == "PENDING"


def test_persist_transition_updates_search_and_success_states() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    repository = ServiceNowLinkageRetrySqlRepository(engine=engine)
    repository.ensure_schema()
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    pending = repository.get_or_create_pending(
        case_id="case-sn-002",
        pd_incident_id="pd-inc-002",
        incident_sys_id="inc-002",
        retry_window_minutes=120,
        now=now,
    )
    searching = mark_linkage_searching(record=pending, now=now + timedelta(seconds=1))
    persisted_searching = repository.persist_transition(
        case_id=pending.case_id,
        next_record=searching,
        expected_source_statuses={"PENDING"},
    )
    linked = mark_linkage_success(
        record=persisted_searching,
        request_id="req-1",
        incident_sys_id="inc-002",
        now=now + timedelta(seconds=2),
    )
    persisted_linked = repository.persist_transition(
        case_id=pending.case_id,
        next_record=linked,
        expected_source_statuses={"SEARCHING"},
    )

    assert persisted_linked.state == "LINKED"
    assert persisted_linked.attempt_count == 1
    assert persisted_linked.request_id == "req-1"


def test_select_retry_candidates_returns_only_due_failed_temp_records() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    repository = ServiceNowLinkageRetrySqlRepository(engine=engine)
    repository.ensure_schema()
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    pending_due = repository.get_or_create_pending(
        case_id="case-sn-due",
        pd_incident_id="pd-inc-due",
        incident_sys_id="inc-due",
        retry_window_minutes=120,
        now=now,
    )
    searching_due = repository.persist_transition(
        case_id=pending_due.case_id,
        next_record=mark_linkage_searching(record=pending_due, now=now),
        expected_source_statuses={"PENDING"},
    )
    failed_due = mark_linkage_failure(
        record=searching_due,
        transient=True,
        error_code="timeout",
        error_message="timed out",
        request_id="req-due",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=now,
    )
    repository.persist_transition(
        case_id=pending_due.case_id,
        next_record=failed_due,
        expected_source_statuses={"SEARCHING"},
    )

    pending_future = repository.get_or_create_pending(
        case_id="case-sn-future",
        pd_incident_id="pd-inc-future",
        incident_sys_id="inc-future",
        retry_window_minutes=120,
        now=now,
    )
    searching_future = repository.persist_transition(
        case_id=pending_future.case_id,
        next_record=mark_linkage_searching(record=pending_future, now=now),
        expected_source_statuses={"PENDING"},
    )
    failed_future = mark_linkage_failure(
        record=searching_future,
        transient=True,
        error_code="timeout",
        error_message="timed out",
        request_id="req-future",
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
        now=now,
    ).model_copy(update={"next_attempt_at": now + timedelta(hours=1)})
    repository.persist_transition(
        case_id=pending_future.case_id,
        next_record=failed_future,
        expected_source_statuses={"SEARCHING"},
    )

    due_candidates = repository.select_retry_candidates(now=now + timedelta(minutes=5))
    due_case_ids = {record.case_id for record in due_candidates}

    assert "case-sn-due" in due_case_ids
    assert "case-sn-future" not in due_case_ids
