"""Wall-clock evaluation scheduler utilities for evidence collection cadence."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping

from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusClientProtocol,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.pipeline.stages.evidence import (
    collect_evidence_stage_output,
    collect_prometheus_samples,
)


@dataclass(frozen=True)
class SchedulerTick:
    """Single scheduler firing observation used for drift/missed-window handling."""

    expected_boundary: datetime
    actual_fire_time: datetime
    drift_seconds: int
    missed_intervals: int


def floor_to_interval_boundary(timestamp: datetime, interval_seconds: int = 300) -> datetime:
    """Floor timestamp to its wall-clock interval boundary in UTC."""
    utc_ts = timestamp.astimezone(UTC)
    epoch_seconds = int(utc_ts.timestamp())
    floored = epoch_seconds - (epoch_seconds % interval_seconds)
    return datetime.fromtimestamp(floored, tz=UTC)


def next_interval_boundary(timestamp: datetime, interval_seconds: int = 300) -> datetime:
    """Return the next wall-clock interval boundary after the given timestamp."""
    return floor_to_interval_boundary(timestamp, interval_seconds=interval_seconds) + timedelta(
        seconds=interval_seconds
    )


def evaluate_scheduler_tick(
    actual_fire_time: datetime,
    previous_boundary: datetime | None,
    interval_seconds: int = 300,
    drift_threshold_seconds: int = 30,
) -> SchedulerTick:
    """Evaluate scheduler cadence, returning drift and missed interval details."""
    expected_boundary = floor_to_interval_boundary(
        actual_fire_time, interval_seconds=interval_seconds
    )
    drift_seconds = int((actual_fire_time - expected_boundary).total_seconds())

    missed_intervals = 0
    if previous_boundary is not None:
        gap_seconds = int((expected_boundary - previous_boundary).total_seconds())
        missed_intervals = max((gap_seconds // interval_seconds) - 1, 0)
        if missed_intervals > 0:
            get_logger("pipeline.scheduler").warning(
                "scheduler_intervals_missed",
                event_type="scheduler.missed_interval",
                interval_seconds=interval_seconds,
                missed_intervals=missed_intervals,
                previous_boundary=previous_boundary.isoformat(),
                expected_boundary=expected_boundary.isoformat(),
            )

    if drift_seconds > drift_threshold_seconds:
        get_logger("pipeline.scheduler").warning(
            "scheduler_drift_threshold_exceeded",
            event_type="scheduler.drift_warning",
            expected_boundary=expected_boundary.isoformat(),
            actual_fire_time=actual_fire_time.isoformat(),
            drift_seconds=drift_seconds,
            drift_threshold_seconds=drift_threshold_seconds,
        )

    return SchedulerTick(
        expected_boundary=expected_boundary,
        actual_fire_time=actual_fire_time,
        drift_seconds=drift_seconds,
        missed_intervals=missed_intervals,
    )


async def run_evidence_stage_cycle(
    *,
    client: PrometheusClientProtocol,
    metric_queries: Mapping[str, MetricQueryDefinition],
    evaluation_time: datetime,
) -> EvidenceStageOutput:
    """Run Stage 1 evidence collection and anomaly derivation for one scheduler cycle."""
    samples_by_metric = await collect_prometheus_samples(
        client=client,
        metric_queries=metric_queries,
        evaluation_time=evaluation_time,
    )
    return collect_evidence_stage_output(samples_by_metric)
