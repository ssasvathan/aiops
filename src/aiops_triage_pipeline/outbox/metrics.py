"""OTLP metrics for outbox publisher backlog health and publish outcomes."""

from opentelemetry import metrics

_meter = metrics.get_meter("aiops_triage_pipeline.outbox")

_ready_backlog_gauge = _meter.create_up_down_counter(
    name="aiops.outbox.ready_count",
    description="Current count of READY outbox records",
    unit="1",
)
_retry_backlog_gauge = _meter.create_up_down_counter(
    name="aiops.outbox.retry_count",
    description="Current count of RETRY outbox records",
    unit="1",
)
_oldest_ready_age_histogram = _meter.create_histogram(
    name="aiops.outbox.oldest_ready_age_seconds",
    description="Age in seconds of the oldest READY outbox record",
    unit="s",
)
_publish_outcomes = _meter.create_counter(
    name="aiops.outbox.publish_outcomes_total",
    description="Count of outbox publish outcomes by status and outcome",
    unit="1",
)

_prev_ready_count = 0
_prev_retry_count = 0


def record_outbox_backlog_health(
    *,
    ready_count: int,
    retry_count: int,
    oldest_ready_age_seconds: float,
) -> None:
    """Record backlog counts and oldest READY age for outbox health monitoring."""
    global _prev_ready_count
    global _prev_retry_count

    _ready_backlog_gauge.add(ready_count - _prev_ready_count)
    _retry_backlog_gauge.add(retry_count - _prev_retry_count)
    _oldest_ready_age_histogram.record(max(oldest_ready_age_seconds, 0.0))

    _prev_ready_count = ready_count
    _prev_retry_count = retry_count


def record_outbox_publish_outcome(*, status: str, outcome: str) -> None:
    """Record publish outcome counters for sent/retry/dead transitions."""
    _publish_outcomes.add(
        1,
        attributes={
            "status": status,
            "outcome": outcome,
        },
    )
