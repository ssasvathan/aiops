"""Wall-clock scheduler utilities for Stage 1-6 evidence, peak, and gate-decision cycles."""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Sequence

from aiops_triage_pipeline.cache.dedupe import HealthTrackableDedupeStore
from aiops_triage_pipeline.cache.findings_cache import FindingsCacheClientProtocol
from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.health.alerts import (
    OperationalAlertEvaluation,
    OperationalAlertEvaluator,
)
from aiops_triage_pipeline.health.metrics import (
    record_evidence_interval_tick,
    record_pipeline_case_throughput,
    record_pipeline_compute_latency,
    record_prometheus_degraded_active,
    record_prometheus_degraded_transition,
)
from aiops_triage_pipeline.health.registry import HealthRegistry, get_health_registry
from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusClientProtocol,
)
from aiops_triage_pipeline.integrations.slack import SlackClient
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.events import DegradedModeEvent, TelemetryDegradedEvent
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.models.peak import (
    PeakProfile,
    PeakScope,
    PeakStageOutput,
    SustainedIdentityKey,
    SustainedWindowState,
)
from aiops_triage_pipeline.pipeline.baseline_store import BaselineStoreClientProtocol
from aiops_triage_pipeline.pipeline.stages.evidence import (
    collect_evidence_stage_output,
    collect_prometheus_samples_with_diagnostics,
)
from aiops_triage_pipeline.pipeline.stages.gating import (
    GateDedupeStoreProtocol,
    GateInputContext,
    collect_gate_inputs_by_scope,
    enrich_gate_input_context_by_scope,
    evaluate_rulebook_gate_inputs_by_scope,
)
from aiops_triage_pipeline.pipeline.stages.peak import collect_peak_stage_output
from aiops_triage_pipeline.pipeline.stages.topology import (
    TopologyStageOutput,
    collect_topology_stage_output,
)
from aiops_triage_pipeline.registry.loader import TopologyRegistrySnapshot


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
    alert_evaluator: OperationalAlertEvaluator | None = None,
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
    if alert_evaluator is not None:
        alert = alert_evaluator.evaluate_scheduler_drift(drift_seconds=drift_seconds)
        if alert is not None:
            _emit_operational_alert(
                logger=get_logger("pipeline.scheduler"),
                alert=alert,
                drift_seconds=drift_seconds,
                drift_threshold_seconds=drift_threshold_seconds,
                expected_boundary=expected_boundary.isoformat(),
                actual_fire_time=actual_fire_time.isoformat(),
            )

    tick = SchedulerTick(
        expected_boundary=expected_boundary,
        actual_fire_time=actual_fire_time,
        drift_seconds=drift_seconds,
        missed_intervals=missed_intervals,
    )
    record_evidence_interval_tick(
        drift_seconds=drift_seconds,
        missed_intervals=missed_intervals,
        interval_seconds=interval_seconds,
    )
    return tick


async def run_evidence_stage_cycle(
    *,
    client: PrometheusClientProtocol,
    metric_queries: Mapping[str, MetricQueryDefinition],
    evaluation_time: datetime,
    findings_cache_client: FindingsCacheClientProtocol | None = None,
    baseline_cache_client: BaselineStoreClientProtocol | None = None,
    baseline_source: str = "prometheus",
    redis_ttl_policy: RedisTtlPolicyV1 | None = None,
    health_registry: HealthRegistry | None = None,
    alert_evaluator: OperationalAlertEvaluator | None = None,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> EvidenceStageOutput:
    """Run Stage 1 evidence collection and anomaly derivation for one scheduler cycle."""
    started_at = time.perf_counter()
    try:
        diagnostics = await collect_prometheus_samples_with_diagnostics(
            client=client,
            metric_queries=metric_queries,
            evaluation_time=evaluation_time,
        )
        registry = health_registry or get_health_registry()
        previous_prometheus_status = registry.get("prometheus")
        telemetry_degraded_events: tuple[TelemetryDegradedEvent, ...] = ()
        record_prometheus_degraded_active(active=diagnostics.is_total_outage)

        if diagnostics.is_total_outage:
            if previous_prometheus_status != HealthStatus.UNAVAILABLE:
                await registry.update(
                    "prometheus",
                    HealthStatus.UNAVAILABLE,
                    reason=diagnostics.outage_reason,
                )
                record_prometheus_degraded_transition(transition="active")
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
            if alert_evaluator is not None:
                alert = alert_evaluator.record_prometheus_unavailability(is_total_outage=True)
                if alert is not None:
                    _emit_operational_alert(
                        logger=get_logger("pipeline.scheduler"),
                        alert=alert,
                        telemetry_degraded_active=True,
                    )
        elif previous_prometheus_status == HealthStatus.UNAVAILABLE:
            await registry.update("prometheus", HealthStatus.HEALTHY)
            record_prometheus_degraded_transition(transition="cleared")
            telemetry_degraded_events = (
                TelemetryDegradedEvent(
                    affected_scope="prometheus",
                    reason="Prometheus connectivity restored; resuming normal evaluation",
                    recovery_status="resolved",
                    severity="info",
                    timestamp=evaluation_time.astimezone(UTC),
                    ),
                )
            if alert_evaluator is not None:
                alert_evaluator.record_prometheus_unavailability(is_total_outage=False)
        elif alert_evaluator is not None:
            alert_evaluator.record_prometheus_unavailability(is_total_outage=False)

        return collect_evidence_stage_output(
            diagnostics.samples_by_metric,
            findings_cache_client=findings_cache_client,
            baseline_cache_client=baseline_cache_client,
            baseline_source=baseline_source,
            redis_ttl_policy=redis_ttl_policy,
            evaluation_time=evaluation_time,
            telemetry_degraded_active=diagnostics.is_total_outage,
            telemetry_degraded_events=telemetry_degraded_events,
            max_safe_action=Action.NOTIFY if diagnostics.is_total_outage else None,
            anomaly_detection_policy=anomaly_detection_policy,
        )
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        record_pipeline_compute_latency(
            stage="stage1_evidence",
            seconds=elapsed_seconds,
        )
        if alert_evaluator is not None:
            alert = alert_evaluator.evaluate_pipeline_stage_latency(
                seconds=elapsed_seconds,
                stage="stage1_evidence",
            )
            if alert is not None:
                _emit_operational_alert(
                    logger=get_logger("pipeline.scheduler"),
                    alert=alert,
                    stage="stage1_evidence",
                )


def run_peak_stage_cycle(
    *,
    evidence_output: EvidenceStageOutput,
    historical_windows_by_scope: Mapping[PeakScope, Sequence[float]],
    prior_sustained_window_state_by_key: (
        Mapping[SustainedIdentityKey, SustainedWindowState] | None
    ) = None,
    cached_peak_profiles_by_scope: Mapping[PeakScope, PeakProfile] | None = None,
    evaluation_time: datetime,
    peak_policy: PeakPolicyV1 | None = None,
    rulebook_policy: RulebookV1 | None = None,
    sustained_parallel_min_keys: int = 64,
    sustained_parallel_workers: int = 4,
    sustained_parallel_chunk_size: int = 32,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> PeakStageOutput:
    """Run Stage 2 peak classification from Stage 1 normalized rows.

    Pass ``peak_policy`` to avoid disk I/O on every call; omitting it causes
    the policy to be loaded from the default file path each time.
    """
    started_at = time.perf_counter()
    try:
        return collect_peak_stage_output(
            rows=evidence_output.rows,
            historical_windows_by_scope=historical_windows_by_scope,
            evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
            anomaly_findings=evidence_output.anomaly_result.findings,
            prior_sustained_window_state_by_key=prior_sustained_window_state_by_key,
            cached_profiles_by_scope=cached_peak_profiles_by_scope,
            evaluation_time=evaluation_time,
            peak_policy=peak_policy,
            rulebook_policy=rulebook_policy,
            sustained_parallel_min_keys=sustained_parallel_min_keys,
            sustained_parallel_workers=sustained_parallel_workers,
            sustained_parallel_chunk_size=sustained_parallel_chunk_size,
        )
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        record_pipeline_compute_latency(
            stage="stage2_peak",
            seconds=elapsed_seconds,
        )
        if alert_evaluator is not None:
            alert = alert_evaluator.evaluate_pipeline_stage_latency(
                seconds=elapsed_seconds,
                stage="stage2_peak",
            )
            if alert is not None:
                _emit_operational_alert(
                    logger=get_logger("pipeline.scheduler"),
                    alert=alert,
                    stage="stage2_peak",
                )


def run_topology_stage_cycle(
    *,
    evidence_output: EvidenceStageOutput,
    snapshot: TopologyRegistrySnapshot,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> TopologyStageOutput:
    """Run Stage 3 topology resolution from Stage 1 findings."""
    started_at = time.perf_counter()
    try:
        return collect_topology_stage_output(
            snapshot=snapshot,
            evidence_output=evidence_output,
        )
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        record_pipeline_compute_latency(
            stage="stage3_topology",
            seconds=elapsed_seconds,
        )
        if alert_evaluator is not None:
            alert = alert_evaluator.evaluate_pipeline_stage_latency(
                seconds=elapsed_seconds,
                stage="stage3_topology",
            )
            if alert is not None:
                _emit_operational_alert(
                    logger=get_logger("pipeline.scheduler"),
                    alert=alert,
                    stage="stage3_topology",
                )


def run_gate_input_stage_cycle(
    *,
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    context_by_scope: Mapping[tuple[str, ...], GateInputContext],
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> dict[tuple[str, ...], tuple[GateInputV1, ...]]:
    """Run Stage 6 gate-input assembly from Stage 1 and Stage 2 outputs."""
    started_at = time.perf_counter()
    try:
        scopes_without_context = [
            scope
            for scope in evidence_output.gate_findings_by_scope
            if not _has_gate_input_context(scope=scope, context_by_scope=context_by_scope)
        ]
        if scopes_without_context:
            get_logger("pipeline.scheduler").warning(
                "gate_input_scope_context_missing",
                event_type="scheduler.gate_input_scope_skipped_unresolved",
                skipped_scopes=tuple(sorted(scopes_without_context)),
                skipped_scope_count=len(scopes_without_context),
            )

        gate_findings_by_scope = {
            scope: findings
            for scope, findings in evidence_output.gate_findings_by_scope.items()
            if _has_gate_input_context(scope=scope, context_by_scope=context_by_scope)
        }
        filtered_evidence_output = EvidenceStageOutput(
            rows=evidence_output.rows,
            anomaly_result=evidence_output.anomaly_result,
            gate_findings_by_scope=gate_findings_by_scope,
            evidence_status_map_by_scope={
                scope: evidence_output.evidence_status_map_by_scope.get(scope, {})
                for scope in gate_findings_by_scope
            },
            telemetry_degraded_active=evidence_output.telemetry_degraded_active,
            telemetry_degraded_events=evidence_output.telemetry_degraded_events,
            max_safe_action=evidence_output.max_safe_action,
        )
        enriched_context_by_scope = enrich_gate_input_context_by_scope(
            evidence_output=filtered_evidence_output,
            peak_output=peak_output,
            context_by_scope=context_by_scope,
            max_safe_action=filtered_evidence_output.max_safe_action,
        )
        return collect_gate_inputs_by_scope(
            evidence_output=filtered_evidence_output,
            peak_output=peak_output,
            context_by_scope=enriched_context_by_scope,
            max_safe_action=filtered_evidence_output.max_safe_action,
        )
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        record_pipeline_compute_latency(
            stage="stage4_gate_input",
            seconds=elapsed_seconds,
        )
        if alert_evaluator is not None:
            alert = alert_evaluator.evaluate_pipeline_stage_latency(
                seconds=elapsed_seconds,
                stage="stage4_gate_input",
            )
            if alert is not None:
                _emit_operational_alert(
                    logger=get_logger("pipeline.scheduler"),
                    alert=alert,
                    stage="stage4_gate_input",
                )


def run_gate_decision_stage_cycle(
    *,
    gate_inputs_by_scope: Mapping[tuple[str, ...], tuple[GateInputV1, ...]],
    rulebook_policy: RulebookV1 | None = None,
    dedupe_store: GateDedupeStoreProtocol | None = None,
    latency_warning_threshold_ms: int = 500,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> dict[tuple[str, ...], tuple[ActionDecisionV1, ...]]:
    """Run Stage 6 rulebook decision evaluation for assembled gate inputs."""
    started_at = time.perf_counter()
    if rulebook_policy is None:
        raise ValueError(
            "rulebook_policy is required for run_gate_decision_stage_cycle "
            "to avoid implicit policy file I/O"
        )
    try:
        decisions_by_scope = evaluate_rulebook_gate_inputs_by_scope(
            gate_inputs_by_scope=gate_inputs_by_scope,
            rulebook=rulebook_policy,
            dedupe_store=dedupe_store,
            latency_warning_threshold_ms=latency_warning_threshold_ms,
        )
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        record_pipeline_compute_latency(
            stage="stage5_gate_decision",
            seconds=elapsed_seconds,
        )
        if alert_evaluator is not None:
            alert = alert_evaluator.evaluate_pipeline_stage_latency(
                seconds=elapsed_seconds,
                stage="stage5_gate_decision",
            )
            if alert is not None:
                _emit_operational_alert(
                    logger=get_logger("pipeline.scheduler"),
                    alert=alert,
                    stage="stage5_gate_decision",
                )

    produced_cases = sum(len(decisions) for decisions in decisions_by_scope.values())
    record_pipeline_case_throughput(case_count=produced_cases)
    return decisions_by_scope


async def emit_redis_degraded_mode_events(
    *,
    dedupe_store: GateDedupeStoreProtocol | None,
    evaluation_time: datetime,
    health_registry: HealthRegistry | None = None,
    slack_client: SlackClient | None = None,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> tuple[DegradedModeEvent, ...]:
    """Emit DegradedModeEvent and update HealthRegistry when Redis is degraded.

    Mirrors the Prometheus degradation pattern in ``run_evidence_stage_cycle``:
    - On first Redis failure: update HealthRegistry to DEGRADED, emit event,
      send to Slack if configured.
    - On continued failure: suppress duplicate events (registry already DEGRADED).
    - On recovery: update HealthRegistry back to HEALTHY; no event emitted.
    - When dedupe_store is None or not health-trackable: no-op.

    Args:
        dedupe_store:    The AG5 dedupe store used in the previous gate cycle.
        evaluation_time: UTC timestamp of the current evaluation cycle.
        health_registry: Registry to update. Defaults to the process singleton.
        slack_client:    Slack client for degraded-mode notifications.

    Returns:
        Tuple of emitted DegradedModeEvent instances (0 or 1 per cycle).
    """
    if not isinstance(dedupe_store, HealthTrackableDedupeStore):
        return ()

    registry = health_registry or get_health_registry()
    previous_redis_status = registry.get("redis")
    logger = get_logger("pipeline.scheduler")

    if not dedupe_store.is_healthy:
        if previous_redis_status not in (HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE):
            await registry.update(
                "redis",
                HealthStatus.DEGRADED,
                reason=dedupe_store.last_error,
            )
            event = DegradedModeEvent(
                affected_scope="redis",
                reason=dedupe_store.last_error or "Redis dedupe store unavailable",
                capped_action_level="NOTIFY-only",
                estimated_impact_window="unknown",
                timestamp=evaluation_time.astimezone(UTC),
            )
            logger.warning(
                "redis_degraded_mode_event",
                event_type="DegradedModeEvent",
                affected_scope=event.affected_scope,
                reason=event.reason,
                capped_action_level=event.capped_action_level,
                estimated_impact_window=event.estimated_impact_window,
                timestamp=event.timestamp.isoformat(),
            )
            if alert_evaluator is not None:
                alert = alert_evaluator.evaluate_redis_connection(healthy=False)
                if alert is not None:
                    _emit_operational_alert(
                        logger=logger,
                        alert=alert,
                        redis_health="degraded",
                    )
            if slack_client is not None:
                await asyncio.to_thread(slack_client.send_degraded_mode_event, event)
            return (event,)
        return ()

    if previous_redis_status in (HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE):
        await registry.update("redis", HealthStatus.HEALTHY)
        logger.info(
            "redis_degraded_mode_recovered",
            event_type="scheduler.redis_recovery",
            previous_status=previous_redis_status.value,
        )
    return ()


def _emit_operational_alert(
    *,
    logger,
    alert: OperationalAlertEvaluation,
    **fields: object,
) -> None:
    log_fn = logger.critical if alert.severity == "critical" else logger.warning
    payload: dict[str, object] = {
        "event_type": "operational_alert_rule_triggered",
        "rule_id": alert.rule_id,
        "component": alert.component,
        "severity": alert.severity,
        "condition": alert.condition,
        "recommended_action": alert.recommended_action,
        "observed_value": alert.observed_value,
        "threshold_value": alert.threshold_value,
    }
    payload.update(alert.metadata)
    payload.update(fields)
    log_fn(
        "operational_alert_rule_triggered",
        **payload,
    )


def _has_gate_input_context(
    *,
    scope: tuple[str, ...],
    context_by_scope: Mapping[tuple[str, ...], GateInputContext],
) -> bool:
    if scope in context_by_scope:
        return True
    if len(scope) == 4:
        topic_scope = (scope[0], scope[1], scope[3])
        return topic_scope in context_by_scope
    return False
