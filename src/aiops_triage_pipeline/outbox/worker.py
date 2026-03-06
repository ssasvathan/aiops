"""Durable outbox publisher loop for READY/RETRY recovery and Kafka emission."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.outbox.publisher import (
    CaseEventPublisherProtocol,
    publish_case_events_after_invariant_a,
)
from aiops_triage_pipeline.outbox.schema import OutboxRecordV1
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

_READY_WARN_AGE_SECONDS = 120.0
_READY_CRITICAL_AGE_SECONDS = 600.0


class OutboxRepositoryPublishProtocol(Protocol):
    """Repository interface needed by the outbox worker."""

    def select_publishable(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[OutboxRecordV1]: ...

    def transition_to_sent(
        self,
        *,
        case_id: str,
        now: datetime | None = None,
    ) -> OutboxRecordV1: ...

    def transition_publish_failure(
        self,
        *,
        case_id: str,
        policy: OutboxPolicyV1,
        app_env: str,
        error_message: str,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> OutboxRecordV1: ...


@dataclass(frozen=True)
class OutboxWorkerIterationResult:
    """Outcome counters from a single outbox publisher polling iteration."""

    scanned_count: int
    sent_count: int
    failed_count: int


class OutboxPublisherWorker:
    """Poll publishable outbox rows and transition durable state on publish outcomes."""

    def __init__(
        self,
        *,
        outbox_repository: OutboxRepositoryPublishProtocol,
        object_store_client: ObjectStoreClientProtocol,
        publisher: CaseEventPublisherProtocol,
        policy: OutboxPolicyV1,
        app_env: str,
        batch_size: int = 100,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")

        self._outbox_repository = outbox_repository
        self._object_store_client = object_store_client
        self._publisher = publisher
        self._policy = policy
        self._app_env = app_env
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds
        self._logger = get_logger("outbox.worker")

    def run_once(self, *, now: datetime | None = None) -> OutboxWorkerIterationResult:
        """Run a single publish attempt loop for currently publishable records."""
        resolved_now = _resolve_now(now)
        publishable = self._outbox_repository.select_publishable(
            now=resolved_now,
            limit=self._batch_size,
        )
        self._emit_backlog_health_logs(now=resolved_now, records=publishable)

        sent_count = 0
        failed_count = 0

        for record in publishable:
            try:
                evidence = publish_case_events_after_invariant_a(
                    outbox_record=record,
                    object_store_client=self._object_store_client,
                    publisher=self._publisher,
                    published_at=resolved_now,
                )
                sent_record = self._outbox_repository.transition_to_sent(
                    case_id=record.case_id,
                    now=evidence.published_at,
                )
                self._logger.info(
                    "outbox_publish_succeeded",
                    event_type="outbox.publish_succeeded",
                    case_id=record.case_id,
                    status=sent_record.status,
                    delivery_attempts=sent_record.delivery_attempts,
                    event_count=evidence.event_count,
                    published_at=evidence.published_at.isoformat(),
                )
                sent_count += 1
            except Exception as exc:  # noqa: BLE001
                failed_record = self._outbox_repository.transition_publish_failure(
                    case_id=record.case_id,
                    policy=self._policy,
                    app_env=self._app_env,
                    error_message=str(exc),
                    error_code=type(exc).__name__,
                    now=resolved_now,
                )
                failed_count += 1
                self._log_publish_failure(record=failed_record, exc=exc)

        return OutboxWorkerIterationResult(
            scanned_count=len(publishable),
            sent_count=sent_count,
            failed_count=failed_count,
        )

    def run_forever(self) -> None:
        """Run the outbox worker loop continuously."""
        while True:
            self.run_once()
            time.sleep(self._poll_interval_seconds)

    def _emit_backlog_health_logs(self, *, now: datetime, records: list[OutboxRecordV1]) -> None:
        ready_records = [record for record in records if record.status == "READY"]
        retry_records = [record for record in records if record.status == "RETRY"]
        oldest_ready_age_seconds = (
            max((now - record.updated_at).total_seconds() for record in ready_records)
            if ready_records
            else 0.0
        )

        if oldest_ready_age_seconds >= _READY_CRITICAL_AGE_SECONDS:
            log_fn = self._logger.critical
            severity = "critical"
        elif oldest_ready_age_seconds >= _READY_WARN_AGE_SECONDS:
            log_fn = self._logger.warning
            severity = "warning"
        else:
            log_fn = self._logger.info
            severity = "info"

        log_fn(
            "outbox_backlog_health",
            event_type="outbox.backlog_health",
            ready_count=len(ready_records),
            retry_count=len(retry_records),
            oldest_ready_age_seconds=oldest_ready_age_seconds,
            threshold_state=severity,
        )

    def _log_publish_failure(self, *, record: OutboxRecordV1, exc: Exception) -> None:
        if record.status == "DEAD":
            log_fn = self._logger.critical
        else:
            log_fn = self._logger.warning
        log_fn(
            "outbox_publish_failed",
            event_type="outbox.publish_failed",
            case_id=record.case_id,
            status=record.status,
            delivery_attempts=record.delivery_attempts,
            next_attempt_at=(
                None if record.next_attempt_at is None else record.next_attempt_at.isoformat()
            ),
            error_code=record.last_error_code or type(exc).__name__,
            error_message=record.last_error_message or str(exc),
        )


def _resolve_now(now: datetime | None) -> datetime:
    resolved_now = now or datetime.now(tz=UTC)
    if resolved_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return resolved_now
