"""Durable outbox publisher loop for READY/RETRY recovery and Kafka emission."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import Protocol

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.errors.exceptions import (
    DenylistSanitizationError,
    PublishAfterDenylistError,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.outbox.metrics import (
    record_outbox_delivery_slo_breach,
    record_outbox_health_snapshot,
    record_outbox_publish_latency,
    record_outbox_publish_outcome,
)
from aiops_triage_pipeline.outbox.publisher import (
    CaseEventPublisherProtocol,
    publish_case_events_after_invariant_a,
)
from aiops_triage_pipeline.outbox.repository import OutboxHealthSnapshot
from aiops_triage_pipeline.outbox.schema import OutboxRecordV1
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

_DELIVERY_LATENCY_SAMPLE_WINDOW = 1000


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

    def select_backlog_health(
        self,
        *,
        now: datetime | None = None,
    ) -> OutboxHealthSnapshot: ...


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
        denylist: DenylistV1,
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
        self._denylist = denylist
        self._policy = policy
        self._app_env = app_env
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds
        self._logger = get_logger("outbox.worker")
        self._delivery_latency_samples_seconds: list[float] = []

    def run_once(self, *, now: datetime | None = None) -> OutboxWorkerIterationResult:
        """Run a single publish attempt loop for currently publishable records."""
        resolved_now = _resolve_now(now)
        publishable = self._outbox_repository.select_publishable(
            now=resolved_now,
            limit=self._batch_size,
        )
        self._emit_backlog_health_logs(now=resolved_now)

        sent_count = 0
        failed_count = 0

        for record in publishable:
            try:
                evidence = publish_case_events_after_invariant_a(
                    outbox_record=record,
                    object_store_client=self._object_store_client,
                    publisher=self._publisher,
                    denylist=self._denylist,
                    published_at=resolved_now,
                )
                sent_record = self._outbox_repository.transition_to_sent(
                    case_id=record.case_id,
                    now=evidence.published_at,
                )
                self._logger.info(
                    "outbox_denylist_applied",
                    event_type="outbox.denylist_applied",
                    case_id=record.case_id,
                    component="outbox.worker",
                    boundary_id=evidence.boundary_id,
                    outcome="success",
                    severity="info",
                    removed_field_count=evidence.removed_field_count,
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
                latency_seconds = max(
                    (evidence.published_at - record.created_at).total_seconds(),
                    0.0,
                )
                record_outbox_publish_latency(seconds=latency_seconds)
                self._record_delivery_latency_sample(seconds=latency_seconds)
                self._evaluate_delivery_slo(now=evidence.published_at)
                record_outbox_publish_outcome(status=sent_record.status, outcome="success")
                sent_count += 1
            except Exception as exc:  # noqa: BLE001
                error_code = type(exc).__name__
                if isinstance(exc, PublishAfterDenylistError):
                    error_code = exc.error_code
                failed_record = self._outbox_repository.transition_publish_failure(
                    case_id=record.case_id,
                    policy=self._policy,
                    app_env=self._app_env,
                    error_message=str(exc),
                    error_code=error_code,
                    now=resolved_now,
                )
                failed_count += 1
                self._log_denylist_outcome_on_failure(record=failed_record, exc=exc)
                self._log_publish_failure(record=failed_record, exc=exc)
                record_outbox_publish_outcome(status=failed_record.status, outcome="failure")

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

    def _emit_backlog_health_logs(self, *, now: datetime) -> None:
        health = self._outbox_repository.select_backlog_health(now=now)
        severity = self._resolve_backlog_health_severity(health=health)
        if severity == "critical":
            log_fn = self._logger.critical
        elif severity == "warning":
            log_fn = self._logger.warning
        else:
            log_fn = self._logger.info

        log_fn(
            "outbox_backlog_health",
            event_type="outbox.backlog_health",
            pending_object_count=health.pending_object_count,
            ready_count=health.ready_count,
            retry_count=health.retry_count,
            dead_count=health.dead_count,
            sent_count=health.sent_count,
            oldest_pending_object_age_seconds=health.oldest_pending_object_age_seconds,
            oldest_ready_age_seconds=health.oldest_ready_age_seconds,
            oldest_retry_age_seconds=health.oldest_retry_age_seconds,
            oldest_dead_age_seconds=health.oldest_dead_age_seconds,
            threshold_state=severity,
        )
        record_outbox_health_snapshot(snapshot=health)
        self._emit_state_age_threshold_breaches(health=health)
        self._emit_dead_count_threshold_breach(health=health)

    def _resolve_backlog_health_severity(self, *, health: OutboxHealthSnapshot) -> str:
        severity = "info"
        threshold_by_state = (
            (
                health.oldest_pending_object_age_seconds,
                self._policy.state_age_thresholds.pending_object.warning_seconds,
                self._policy.state_age_thresholds.pending_object.critical_seconds,
            ),
            (
                health.oldest_ready_age_seconds,
                self._policy.state_age_thresholds.ready.warning_seconds,
                self._policy.state_age_thresholds.ready.critical_seconds,
            ),
            (
                health.oldest_retry_age_seconds,
                self._policy.state_age_thresholds.retry.warning_seconds,
                self._policy.state_age_thresholds.retry.critical_seconds,
            ),
        )
        for actual_age, warning_threshold, critical_threshold in threshold_by_state:
            if actual_age > critical_threshold:
                return "critical"
            if warning_threshold is not None and actual_age > warning_threshold:
                severity = "warning"

        dead_threshold = self._policy.dead_count_critical_threshold.get(self._app_env, 0)
        if health.dead_count > dead_threshold:
            if self._app_env == "prod":
                return "critical"
            return "warning"
        return severity

    def _emit_state_age_threshold_breaches(self, *, health: OutboxHealthSnapshot) -> None:
        threshold_by_state = (
            (
                "PENDING_OBJECT",
                health.oldest_pending_object_age_seconds,
                self._policy.state_age_thresholds.pending_object.warning_seconds,
                self._policy.state_age_thresholds.pending_object.critical_seconds,
            ),
            (
                "READY",
                health.oldest_ready_age_seconds,
                self._policy.state_age_thresholds.ready.warning_seconds,
                self._policy.state_age_thresholds.ready.critical_seconds,
            ),
            (
                "RETRY",
                health.oldest_retry_age_seconds,
                self._policy.state_age_thresholds.retry.warning_seconds,
                self._policy.state_age_thresholds.retry.critical_seconds,
            ),
        )
        for state, actual_age, warning_threshold, critical_threshold in threshold_by_state:
            severity: str | None = None
            threshold_value = critical_threshold
            if actual_age > critical_threshold:
                severity = "critical"
            elif warning_threshold is not None and actual_age > warning_threshold:
                severity = "warning"
                threshold_value = warning_threshold
            if severity is None:
                continue
            log_fn = self._logger.critical if severity == "critical" else self._logger.warning
            log_fn(
                "outbox_health_threshold_breach",
                event_type="outbox.health.threshold_breach",
                state=state,
                severity=severity,
                actual_value=actual_age,
                threshold_value=threshold_value,
                app_env=self._app_env,
            )

    def _emit_dead_count_threshold_breach(self, *, health: OutboxHealthSnapshot) -> None:
        critical_threshold = self._policy.dead_count_critical_threshold.get(self._app_env, 0)
        if health.dead_count <= critical_threshold:
            return

        if self._app_env == "prod":
            log_fn = self._logger.critical
            severity = "critical"
        else:
            log_fn = self._logger.warning
            severity = "warning"
        log_fn(
            "outbox_health_threshold_breach",
            event_type="outbox.health.threshold_breach",
            state="DEAD",
            severity=severity,
            actual_value=float(health.dead_count),
            threshold_value=float(critical_threshold),
            app_env=self._app_env,
        )
        log_fn(
            "outbox_dead_manual_resolution_required",
            event_type="outbox.dead.manual_resolution_required",
            dead_count=health.dead_count,
            app_env=self._app_env,
            message="DEAD records require human investigation and explicit replay/resolution.",
        )

    def _record_delivery_latency_sample(self, *, seconds: float) -> None:
        self._delivery_latency_samples_seconds.append(max(seconds, 0.0))
        if len(self._delivery_latency_samples_seconds) > _DELIVERY_LATENCY_SAMPLE_WINDOW:
            self._delivery_latency_samples_seconds = self._delivery_latency_samples_seconds[
                -_DELIVERY_LATENCY_SAMPLE_WINDOW:
            ]

    def _evaluate_delivery_slo(self, *, now: datetime) -> None:
        if not self._delivery_latency_samples_seconds:
            return
        slo = self._policy.delivery_slo
        p95_seconds = _nearest_rank_percentile(self._delivery_latency_samples_seconds, 0.95)
        p99_seconds = _nearest_rank_percentile(self._delivery_latency_samples_seconds, 0.99)

        if p95_seconds > slo.p95_target_seconds:
            self._logger.warning(
                "outbox_health_threshold_breach",
                event_type="outbox.health.threshold_breach",
                state="DELIVERY_SLO_P95",
                severity="warning",
                actual_value=p95_seconds,
                threshold_value=slo.p95_target_seconds,
                app_env=self._app_env,
                measured_at=now.isoformat(),
            )
            record_outbox_delivery_slo_breach(severity="warning", quantile="p95")

        if p99_seconds > slo.p99_critical_seconds:
            severity = "critical"
            threshold_value = slo.p99_critical_seconds
        elif p99_seconds > slo.p99_target_seconds:
            severity = "warning"
            threshold_value = slo.p99_target_seconds
        else:
            return

        log_fn = self._logger.critical if severity == "critical" else self._logger.warning
        log_fn(
            "outbox_health_threshold_breach",
            event_type="outbox.health.threshold_breach",
            state="DELIVERY_SLO_P99",
            severity=severity,
            actual_value=p99_seconds,
            threshold_value=threshold_value,
            app_env=self._app_env,
            measured_at=now.isoformat(),
        )
        record_outbox_delivery_slo_breach(severity=severity, quantile="p99")

    def _log_publish_failure(self, *, record: OutboxRecordV1, exc: Exception) -> None:
        extra_fields: dict[str, object] = {}
        if record.status == "DEAD":
            log_fn = self._logger.critical
            extra_fields = {
                "human_investigation_required": True,
                "manual_replay_required": True,
                "resolution_guidance": (
                    "DEAD is terminal in automated flow; "
                    "human investigation and explicit replay are required."
                ),
            }
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
            **extra_fields,
        )

    def _log_denylist_outcome_on_failure(self, *, record: OutboxRecordV1, exc: Exception) -> None:
        if isinstance(exc, DenylistSanitizationError):
            self._logger.warning(
                "outbox_denylist_applied",
                event_type="outbox.denylist_applied",
                case_id=record.case_id,
                component="outbox.worker",
                boundary_id=exc.boundary_id,
                outcome="failure",
                severity="warning",
                removed_field_count=exc.removed_field_count,
                error_code=type(exc).__name__,
            )
            return
        if isinstance(exc, PublishAfterDenylistError):
            self._logger.warning(
                "outbox_denylist_applied",
                event_type="outbox.denylist_applied",
                case_id=record.case_id,
                component="outbox.worker",
                boundary_id=exc.boundary_id,
                outcome="applied_publish_failed",
                severity="warning",
                removed_field_count=exc.removed_field_count,
                error_code=exc.error_code,
            )


def _resolve_now(now: datetime | None) -> datetime:
    resolved_now = now or datetime.now(tz=UTC)
    if resolved_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return resolved_now


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if percentile <= 0:
        return min(values)
    if percentile >= 1:
        return max(values)
    ordered = sorted(values)
    rank = ceil(percentile * len(ordered))
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[index]
