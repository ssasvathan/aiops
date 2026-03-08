from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1, OutboxRetentionPolicy
from aiops_triage_pipeline.outbox.repository import OutboxHealthSnapshot, OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, create_outbox_table


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
