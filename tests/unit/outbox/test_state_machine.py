from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1
from aiops_triage_pipeline.outbox.state_machine import (
    create_ready_outbox_record,
    mark_outbox_record_sent,
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

    with pytest.raises(ValueError, match="cannot mark record SENT"):
        mark_outbox_record_sent(record=non_ready_record)
