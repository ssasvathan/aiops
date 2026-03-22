from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, update

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1, OutboxRetentionPolicy
from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.outbox.repository import OutboxHealthSnapshot, OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import (
    OutboxReadyCasefileV1,
    create_outbox_table,
    outbox_table,
)


def _policy_for_tests() -> OutboxPolicyV1:
    return OutboxPolicyV1(
        retention_by_env={
            "local": OutboxRetentionPolicy(
                sent_retention_days=1,
                dead_retention_days=7,
                max_retry_attempts=1,
            ),
            "dev": OutboxRetentionPolicy(sent_retention_days=3, dead_retention_days=14),
            "uat": OutboxRetentionPolicy(sent_retention_days=7, dead_retention_days=30),
            "prod": OutboxRetentionPolicy(sent_retention_days=14, dead_retention_days=90),
        }
    )


def _ready_casefile(case_id: str) -> OutboxReadyCasefileV1:
    return OutboxReadyCasefileV1(
        case_id=case_id,
        object_path=f"cases/{case_id}/triage.json",
        triage_hash="a" * 64,
    )


def test_select_backlog_health_returns_multi_state_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    base = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)

    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-pending"), now=base)

    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-ready"), now=base)
    repository.transition_to_ready(case_id="case-ready", now=base)

    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-retry"), now=base)
    repository.transition_to_ready(case_id="case-retry", now=base)
    repository.transition_publish_failure(
        case_id="case-retry",
        policy=_policy_for_tests(),
        app_env="local",
        error_message="kafka unavailable",
        now=base,
    )

    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-dead"), now=base)
    repository.transition_to_ready(case_id="case-dead", now=base)
    repository.transition_publish_failure(
        case_id="case-dead",
        policy=_policy_for_tests(),
        app_env="local",
        error_message="kafka unavailable",
        now=base,
    )
    repository.transition_publish_failure(
        case_id="case-dead",
        policy=_policy_for_tests(),
        app_env="local",
        error_message="kafka unavailable",
        now=base,
    )

    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-sent"), now=base)
    repository.transition_to_ready(case_id="case-sent", now=base)
    repository.transition_to_sent(case_id="case-sent", now=base)

    snapshot = repository.select_backlog_health(now=base)

    assert isinstance(snapshot, OutboxHealthSnapshot)
    assert snapshot.pending_object_count == 1
    assert snapshot.ready_count == 1
    assert snapshot.retry_count == 1
    assert snapshot.dead_count == 1
    assert snapshot.sent_count == 1
    assert snapshot.oldest_pending_object_age_seconds == 0.0
    assert snapshot.oldest_ready_age_seconds == 0.0
    assert snapshot.oldest_retry_age_seconds == 0.0
    assert snapshot.oldest_dead_age_seconds == 0.0


def test_select_backlog_health_clamps_negative_ages_to_zero() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    insert_time = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    earlier_now = datetime(2026, 3, 6, 11, 59, tzinfo=UTC)

    repository.insert_pending_object(
        confirmed_casefile=_ready_casefile("case-future"),
        now=insert_time,
    )
    snapshot = repository.select_backlog_health(now=earlier_now)

    assert snapshot.pending_object_count == 1
    assert snapshot.oldest_pending_object_age_seconds == 0.0


def test_insert_pending_object_creates_row_in_pending_object_status() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    casefile = _ready_casefile("case-new")

    record = repository.insert_pending_object(confirmed_casefile=casefile, now=now)

    assert record.status == "PENDING_OBJECT"
    assert record.case_id == "case-new"
    assert record.casefile_object_path == casefile.object_path
    assert record.triage_hash == casefile.triage_hash
    assert record.created_at == now
    assert record.updated_at == now
    assert record.delivery_attempts == 0


def test_insert_pending_object_returns_existing_row_when_payload_matches() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    casefile = _ready_casefile("case-idempotent")

    first = repository.insert_pending_object(confirmed_casefile=casefile, now=now)
    second = repository.insert_pending_object(confirmed_casefile=casefile, now=now)

    assert first.case_id == second.case_id
    assert first.triage_hash == second.triage_hash
    assert first.casefile_object_path == second.casefile_object_path
    assert second.status == "PENDING_OBJECT"


def test_insert_pending_object_raises_when_existing_row_has_mismatched_object_path() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    original = _ready_casefile("case-mismatch-path")
    repository.insert_pending_object(confirmed_casefile=original, now=now)

    # Same case_id, same triage_hash, but a different object_path (different sub-path).
    different_path = OutboxReadyCasefileV1(
        case_id="case-mismatch-path",
        object_path="cases/case-mismatch-path-alt/triage.json",
        triage_hash="a" * 64,
    )
    with pytest.raises(InvariantViolation, match="different casefile_object_path"):
        repository.insert_pending_object(confirmed_casefile=different_path, now=now)


def test_insert_pending_object_raises_when_existing_row_has_mismatched_triage_hash() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    original = _ready_casefile("case-mismatch-hash")
    repository.insert_pending_object(confirmed_casefile=original, now=now)

    different_hash = OutboxReadyCasefileV1(
        case_id="case-mismatch-hash",
        object_path="cases/case-mismatch-hash/triage.json",
        triage_hash="c" * 64,
    )
    with pytest.raises(InvariantViolation, match="different triage_hash"):
        repository.insert_pending_object(confirmed_casefile=different_hash, now=now)


def test_transition_to_ready_succeeds_from_pending_object() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-ready-ok"), now=now)
    ready_at = datetime(2026, 3, 22, 10, 1, tzinfo=UTC)

    record = repository.transition_to_ready(case_id="case-ready-ok", now=ready_at)

    assert record.status == "READY"
    assert record.updated_at == ready_at


def test_transition_to_ready_is_idempotent_when_already_ready() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    repository.insert_pending_object(
        confirmed_casefile=_ready_casefile("case-already-ready"), now=now
    )
    repository.transition_to_ready(case_id="case-already-ready", now=now)

    record = repository.transition_to_ready(case_id="case-already-ready", now=now)

    assert record.status == "READY"


def test_transition_to_ready_raises_when_source_status_is_not_pending_object() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    repository.insert_pending_object(confirmed_casefile=_ready_casefile("case-guard"), now=now)
    repository.transition_to_ready(case_id="case-guard", now=now)
    repository.transition_to_sent(case_id="case-guard", now=now)

    with pytest.raises(InvariantViolation, match="cannot mark record READY from status=SENT"):
        repository.transition_to_ready(case_id="case-guard", now=now)


def test_write_transition_raises_when_concurrent_race_leaves_row_in_non_target_status() -> None:
    """SQL-level source-state guard: _write_transition raises InvariantViolation when
    rows_affected == 0 and the current row status is not the target status (concurrent race)."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    casefile = _ready_casefile("case-race")
    repository.insert_pending_object(confirmed_casefile=casefile, now=now)

    # Simulate a concurrent worker that advanced the row to SENT, bypassing in-memory guards.
    with engine.begin() as conn:
        conn.execute(
            update(outbox_table)
            .where(outbox_table.c.case_id == "case-race")
            .values(status="SENT")
        )

    # _write_transition with expected_source_statuses={"PENDING_OBJECT"} should now find
    # 0 rows updated (row is SENT, not PENDING_OBJECT), re-read the row, find SENT != READY,
    # and raise InvariantViolation — the concurrent-race SQL guard safety net.
    current = repository.get_by_case_id("case-race")
    assert current is not None
    # Build a fake READY next_record as if the in-memory guard had passed.
    fake_ready = current.model_copy(update={"status": "READY", "updated_at": now})

    with engine.begin() as conn:
        with pytest.raises(
            InvariantViolation,
            match="outbox transition source-state guard failed",
        ):
            repository._write_transition(  # noqa: SLF001
                conn=conn,
                case_id="case-race",
                next_record=fake_ready,
                expected_source_statuses={"PENDING_OBJECT"},
            )
