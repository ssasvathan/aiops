from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1, OutboxRetentionPolicy
from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1
from aiops_triage_pipeline.outbox.state_machine import (
    create_pending_outbox_record,
    create_ready_outbox_record,
    mark_outbox_record_publish_failure,
    mark_outbox_record_ready,
    mark_outbox_record_sent,
    retention_cutoff_for_state,
)


def _ready_casefile() -> OutboxReadyCasefileV1:
    return OutboxReadyCasefileV1(
        case_id="case-prod-cluster-a-orders-volume-drop",
        object_path="cases/case-prod-cluster-a-orders-volume-drop/triage.json",
        triage_hash="a" * 64,
    )


def test_create_ready_outbox_record_contains_hash_for_tamper_evidence() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)

    record = create_ready_outbox_record(
        confirmed_casefile=_ready_casefile(),
        now=now,
    )

    assert record.status == "READY"
    assert record.case_id == "case-prod-cluster-a-orders-volume-drop"
    assert record.casefile_object_path == "cases/case-prod-cluster-a-orders-volume-drop/triage.json"
    assert record.triage_hash == "a" * 64
    assert record.created_at == now
    assert record.updated_at == now


def test_create_pending_outbox_record_starts_with_pending_object_status() -> None:
    now = datetime(2026, 3, 5, 11, 59, tzinfo=UTC)

    record = create_pending_outbox_record(
        confirmed_casefile=_ready_casefile(),
        now=now,
    )

    assert record.status == "PENDING_OBJECT"
    assert record.casefile_object_path == "cases/case-prod-cluster-a-orders-volume-drop/triage.json"
    assert record.created_at == now
    assert record.updated_at == now
    assert record.delivery_attempts == 0


def test_mark_outbox_record_ready_requires_pending_object_source_state() -> None:
    pending = create_pending_outbox_record(
        confirmed_casefile=_ready_casefile(),
        now=datetime(2026, 3, 5, 11, 59, tzinfo=UTC),
    )
    ready_at = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)

    ready = mark_outbox_record_ready(record=pending, now=ready_at)

    assert ready.status == "READY"
    assert ready.updated_at == ready_at

    with pytest.raises(InvariantViolation, match="cannot mark record READY"):
        mark_outbox_record_ready(record=ready, now=ready_at)


def test_mark_outbox_record_sent_transitions_state_and_increments_attempts() -> None:
    ready_record = create_ready_outbox_record(
        confirmed_casefile=_ready_casefile(),
        now=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
    )
    sent_at = datetime(2026, 3, 5, 12, 1, tzinfo=UTC)

    sent_record = mark_outbox_record_sent(record=ready_record, now=sent_at)

    assert sent_record.status == "SENT"
    assert sent_record.delivery_attempts == 1
    assert sent_record.updated_at == sent_at


def test_mark_outbox_record_sent_rejects_invalid_source_status() -> None:
    non_ready_record = create_ready_outbox_record(confirmed_casefile=_ready_casefile()).model_copy(
        update={"status": "DEAD"}
    )

    with pytest.raises(InvariantViolation, match="cannot mark record SENT"):
        mark_outbox_record_sent(record=non_ready_record)


def test_mark_outbox_record_publish_failure_transitions_to_retry_with_backoff() -> None:
    policy = OutboxPolicyV1(
        retention_by_env={
            "local": OutboxRetentionPolicy(sent_retention_days=1, dead_retention_days=7),
            "dev": OutboxRetentionPolicy(sent_retention_days=3, dead_retention_days=14),
            "uat": OutboxRetentionPolicy(sent_retention_days=7, dead_retention_days=30),
            "prod": OutboxRetentionPolicy(
                sent_retention_days=14,
                dead_retention_days=90,
                max_retry_attempts=5,
            ),
        }
    )
    ready = create_ready_outbox_record(
        confirmed_casefile=_ready_casefile(),
        now=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
    )
    failed_at = datetime(2026, 3, 5, 12, 1, tzinfo=UTC)

    retry = mark_outbox_record_publish_failure(
        record=ready,
        policy=policy,
        app_env="prod",
        error_message="kafka timeout",
        now=failed_at,
    )

    assert retry.status == "RETRY"
    assert retry.delivery_attempts == 1
    assert retry.updated_at == failed_at
    assert retry.next_attempt_at is not None
    assert retry.next_attempt_at > failed_at
    assert retry.last_error_message == "kafka timeout"


def test_mark_outbox_record_publish_failure_transitions_to_dead_after_max_retries() -> None:
    policy = OutboxPolicyV1(
        retention_by_env={
            "local": OutboxRetentionPolicy(sent_retention_days=1, dead_retention_days=7),
            "dev": OutboxRetentionPolicy(sent_retention_days=3, dead_retention_days=14),
            "uat": OutboxRetentionPolicy(sent_retention_days=7, dead_retention_days=30),
            "prod": OutboxRetentionPolicy(
                sent_retention_days=14,
                dead_retention_days=90,
                max_retry_attempts=1,
            ),
        }
    )
    retry = create_ready_outbox_record(
        confirmed_casefile=_ready_casefile(),
        now=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
    ).model_copy(update={"status": "RETRY", "delivery_attempts": 1})
    failed_at = datetime(2026, 3, 5, 12, 2, tzinfo=UTC)

    dead = mark_outbox_record_publish_failure(
        record=retry,
        policy=policy,
        app_env="prod",
        error_message="exceeded retries",
        now=failed_at,
    )

    assert dead.status == "DEAD"
    assert dead.delivery_attempts == 2
    assert dead.updated_at == failed_at
    assert dead.next_attempt_at is None
    assert dead.last_error_message == "exceeded retries"


def test_retention_cutoff_for_state_uses_policy_days() -> None:
    policy = OutboxPolicyV1(
        retention_by_env={
            "local": OutboxRetentionPolicy(sent_retention_days=1, dead_retention_days=7),
            "dev": OutboxRetentionPolicy(sent_retention_days=3, dead_retention_days=14),
            "uat": OutboxRetentionPolicy(sent_retention_days=7, dead_retention_days=30),
            "prod": OutboxRetentionPolicy(
                sent_retention_days=14,
                dead_retention_days=90,
                max_retry_attempts=5,
            ),
        }
    )
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)

    assert retention_cutoff_for_state(policy=policy, app_env="prod", state="SENT", now=now) == (
        datetime(2026, 2, 19, 12, 0, tzinfo=UTC)
    )
    assert retention_cutoff_for_state(policy=policy, app_env="prod", state="DEAD", now=now) == (
        datetime(2025, 12, 5, 12, 0, tzinfo=UTC)
    )
    assert retention_cutoff_for_state(policy=policy, app_env="prod", state="READY", now=now) is None
