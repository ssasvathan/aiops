"""OTLP metrics for outbox publisher health, latency SLOs, and publish outcomes."""

from opentelemetry import metrics

from aiops_triage_pipeline.outbox.repository import OutboxHealthSnapshot

_meter = metrics.get_meter("aiops_triage_pipeline.outbox")

_queue_depth_by_state = _meter.create_up_down_counter(
    name="aiops.outbox.queue_depth",
    description="Current outbox queue depth by state",
    unit="1",
)
_oldest_age_by_state = _meter.create_histogram(
    name="aiops.outbox.oldest_age_seconds",
    description="Age in seconds of the oldest outbox record by monitored state",
    unit="s",
)
_publish_latency_histogram = _meter.create_histogram(
    name="aiops.outbox.casefile_write_to_publish_seconds",
    description="Latency from durable CaseFile write to successful Kafka publish",
    unit="s",
)
_delivery_slo_breach_total = _meter.create_counter(
    name="aiops.outbox.delivery_slo_breaches_total",
    description="Count of delivery SLO threshold breaches by severity and quantile",
    unit="1",
)
_publish_outcomes = _meter.create_counter(
    name="aiops.outbox.publish_outcomes_total",
    description="Count of outbox publish outcomes by status and outcome",
    unit="1",
)

_QUEUE_STATES: tuple[str, ...] = ("PENDING_OBJECT", "READY", "RETRY", "DEAD", "SENT")
_AGE_STATES: tuple[str, ...] = ("PENDING_OBJECT", "READY", "RETRY", "DEAD")

_prev_queue_depth_by_state = {state: 0 for state in _QUEUE_STATES}


def record_outbox_health_snapshot(
    *,
    snapshot: OutboxHealthSnapshot,
) -> None:
    """Record queue depth and oldest-age telemetry across monitored outbox states."""
    current_depth_by_state = {
        "PENDING_OBJECT": snapshot.pending_object_count,
        "READY": snapshot.ready_count,
        "RETRY": snapshot.retry_count,
        "DEAD": snapshot.dead_count,
        "SENT": snapshot.sent_count,
    }
    for state in _QUEUE_STATES:
        previous = _prev_queue_depth_by_state[state]
        current = current_depth_by_state[state]
        _queue_depth_by_state.add(current - previous, attributes={"state": state})
        _prev_queue_depth_by_state[state] = current

    oldest_age_by_state = {
        "PENDING_OBJECT": snapshot.oldest_pending_object_age_seconds,
        "READY": snapshot.oldest_ready_age_seconds,
        "RETRY": snapshot.oldest_retry_age_seconds,
        "DEAD": snapshot.oldest_dead_age_seconds,
    }
    for state in _AGE_STATES:
        _oldest_age_by_state.record(
            max(oldest_age_by_state[state], 0.0),
            attributes={"state": state},
        )


def record_outbox_backlog_health(
    *,
    ready_count: int,
    retry_count: int,
    oldest_ready_age_seconds: float,
) -> None:
    """Backward-compatible helper for READY/RETRY-only backlog telemetry callers."""
    record_outbox_health_snapshot(
        snapshot=OutboxHealthSnapshot(
            pending_object_count=0,
            ready_count=ready_count,
            retry_count=retry_count,
            dead_count=0,
            sent_count=0,
            oldest_pending_object_age_seconds=0.0,
            oldest_ready_age_seconds=oldest_ready_age_seconds,
            oldest_retry_age_seconds=0.0,
            oldest_dead_age_seconds=0.0,
        )
    )


def record_outbox_publish_latency(*, seconds: float) -> None:
    """Record per-record delivery latency from durable write to successful publish."""
    _publish_latency_histogram.record(max(seconds, 0.0))


def record_outbox_delivery_slo_breach(*, severity: str, quantile: str) -> None:
    """Increment delivery SLO breach counter."""
    _delivery_slo_breach_total.add(
        1,
        attributes={
            "severity": severity,
            "quantile": quantile,
        },
    )


def record_outbox_publish_outcome(*, status: str, outcome: str) -> None:
    """Record publish outcome counters for sent/retry/dead transitions."""
    _publish_outcomes.add(
        1,
        attributes={
            "status": status,
            "outcome": outcome,
        },
    )
