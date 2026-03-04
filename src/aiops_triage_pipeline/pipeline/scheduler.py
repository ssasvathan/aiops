"""Wall-clock evaluation scheduler utilities for evidence collection cadence."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Sequence

from aiops_triage_pipeline.cache.findings_cache import FindingsCacheClientProtocol
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.health.registry import HealthRegistry, get_health_registry
from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusClientProtocol,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.events import TelemetryDegradedEvent
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.models.peak import (
    PeakScope,
    PeakStageOutput,
    SustainedIdentityKey,
    SustainedWindowState,
)
from aiops_triage_pipeline.pipeline.stages.evidence import (
    collect_evidence_stage_output,
    collect_prometheus_samples_with_diagnostics,
)
from aiops_triage_pipeline.pipeline.stages.gating import (
    GateInputContext,
    collect_gate_inputs_by_scope,
)
from aiops_triage_pipeline.pipeline.stages.peak import collect_peak_stage_output


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
    findings_cache_client: FindingsCacheClientProtocol | None = None,
    redis_ttl_policy: RedisTtlPolicyV1 | None = None,
    health_registry: HealthRegistry | None = None,
) -> EvidenceStageOutput:
    """Run Stage 1 evidence collection and anomaly derivation for one scheduler cycle."""
    diagnostics = await collect_prometheus_samples_with_diagnostics(
        client=client,
        metric_queries=metric_queries,
        evaluation_time=evaluation_time,
    )
    registry = health_registry or get_health_registry()
    previous_prometheus_status = registry.get("prometheus")
    telemetry_degraded_events: tuple[TelemetryDegradedEvent, ...] = ()

    if diagnostics.is_total_outage:
        if previous_prometheus_status != HealthStatus.UNAVAILABLE:
            await registry.update(
                "prometheus",
                HealthStatus.UNAVAILABLE,
                reason=diagnostics.outage_reason,
            )
            telemetry_degraded_events = (
                TelemetryDegradedEvent(
                    affected_scope="prometheus",
                    reason=diagnostics.outage_reason
                    or "Prometheus source unavailable across the full query set",
                    recovery_status="pending",
                    severity="warning",
                    timestamp=evaluation_time.astimezone(UTC),
                ),
            )
    elif previous_prometheus_status == HealthStatus.UNAVAILABLE:
        await registry.update("prometheus", HealthStatus.HEALTHY)
        telemetry_degraded_events = (
            TelemetryDegradedEvent(
                affected_scope="prometheus",
                reason="Prometheus connectivity restored; resuming normal evaluation",
                recovery_status="resolved",
                severity="info",
                timestamp=evaluation_time.astimezone(UTC),
            ),
        )

    return collect_evidence_stage_output(
        diagnostics.samples_by_metric,
        findings_cache_client=findings_cache_client,
        redis_ttl_policy=redis_ttl_policy,
        evaluation_time=evaluation_time,
        telemetry_degraded_active=diagnostics.is_total_outage,
        telemetry_degraded_events=telemetry_degraded_events,
        max_safe_action=Action.NOTIFY if diagnostics.is_total_outage else None,
    )


def run_peak_stage_cycle(
    *,
    evidence_output: EvidenceStageOutput,
    historical_windows_by_scope: Mapping[PeakScope, Sequence[float]],
    prior_sustained_window_state_by_key: (
        Mapping[SustainedIdentityKey, SustainedWindowState] | None
    ) = None,
    evaluation_time: datetime,
    peak_policy: PeakPolicyV1 | None = None,
    rulebook_policy: RulebookV1 | None = None,
) -> PeakStageOutput:
    """Run Stage 2 peak classification from Stage 1 normalized rows.

    Pass ``peak_policy`` to avoid disk I/O on every call; omitting it causes
    the policy to be loaded from the default file path each time.
    """
    return collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope=historical_windows_by_scope,
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        anomaly_findings=evidence_output.anomaly_result.findings,
        prior_sustained_window_state_by_key=prior_sustained_window_state_by_key,
        evaluation_time=evaluation_time,
        peak_policy=peak_policy,
        rulebook_policy=rulebook_policy,
    )


def run_gate_input_stage_cycle(
    *,
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    context_by_scope: Mapping[tuple[str, ...], GateInputContext],
) -> dict[tuple[str, ...], tuple[GateInputV1, ...]]:
    """Run Stage 6 gate-input assembly from Stage 1 and Stage 2 outputs."""
    return collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope=context_by_scope,
        max_safe_action=evidence_output.max_safe_action,
    )
