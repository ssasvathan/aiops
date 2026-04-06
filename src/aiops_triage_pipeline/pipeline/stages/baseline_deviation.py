"""Baseline deviation stage — detection, correlation, and dedup (Story 2.3).

Implements collect_baseline_deviation_stage_output(), the pipeline composition point that:
1. Reads baseline buckets from SeasonalBaselineClient (Epic 1)
2. Calls compute_modified_z_score() per metric (Story 2.1)
3. Applies correlation gate (MIN_CORRELATED_DEVIATIONS)
4. Applies hand-coded detector dedup (FR14, D6)
5. Emits AnomalyFinding with anomaly_family="BASELINE_DEVIATION" (Story 2.2 models)
6. Returns BaselineDeviationStageOutput (Story 2.2 models)
"""

import time
from collections import defaultdict
from datetime import datetime

import structlog

from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from aiops_triage_pipeline.baseline.computation import (
    MADResult,
    compute_modified_z_score,
    time_to_bucket,
)
from aiops_triage_pipeline.baseline.constants import MIN_CORRELATED_DEVIATIONS
from aiops_triage_pipeline.baseline.models import (
    BaselineDeviationContext,
    BaselineDeviationStageOutput,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.anomaly import AnomalyFinding
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput

HAND_CODED_FAMILIES = frozenset({"CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"})


def collect_baseline_deviation_stage_output(
    *,
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    baseline_client: SeasonalBaselineClient,
    evaluation_time: datetime,
) -> BaselineDeviationStageOutput:
    """Evaluate baseline deviations for all scopes in one pipeline cycle.

    All inputs are explicit keyword-only parameters — no wall clock, no global state.
    This function is fully deterministic: same inputs always produce identical outputs.

    Args:
        evidence_output: Stage 1 output with EvidenceRow observations and hand-coded findings.
        peak_output: Stage 2 output (available but not consumed by detection logic in MVP).
        baseline_client: SeasonalBaselineClient for Redis baseline reads.
        evaluation_time: Injected cycle timestamp — source of (dow, hour) bucket identity.

    Returns:
        BaselineDeviationStageOutput with findings tuple and summary counters.
    """
    logger = get_logger("pipeline.stages.baseline_deviation")

    # Group evidence rows by scope → metric_key → list of values
    metrics_by_scope: dict[tuple[str, ...], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in evidence_output.rows:
        metrics_by_scope[row.scope][row.metric_key].append(row.value)

    scopes = sorted(metrics_by_scope.keys())

    logger.info(
        "baseline_deviation_stage_started",
        event_type="baseline_deviation.stage_started",
        scopes_count=len(scopes),
        evaluation_time=evaluation_time.isoformat(),
    )

    started_at = time.perf_counter()
    hand_coded_scopes = _build_hand_coded_dedup_set(evidence_output)
    dow, hour = time_to_bucket(evaluation_time)

    findings: list[AnomalyFinding] = []
    scopes_evaluated = 0
    deviations_detected = 0
    deviations_suppressed_single_metric = 0
    deviations_suppressed_dedup = 0

    try:
        for scope in scopes:
            scopes_evaluated += 1
            scope_metrics = metrics_by_scope[scope]

            # Hand-coded dedup check (FR14, D6): skip before Redis read for efficiency
            if scope in hand_coded_scopes:
                logger.info(
                    "baseline_deviation_suppressed_dedup",
                    event_type="baseline_deviation.suppressed_dedup",
                    scope=scope,
                    reason="HAND_CODED_DETECTOR_FIRED",
                )
                deviations_suppressed_dedup += 1
                continue

            try:
                result = _evaluate_scope(
                    scope=scope,
                    scope_metrics=scope_metrics,
                    baseline_client=baseline_client,
                    dow=dow,
                    hour=hour,
                    evaluation_time=evaluation_time,
                    logger=logger,
                )
            except (ConnectionError, OSError, TimeoutError):
                # Network/Redis-level errors propagate to the outer handler as fail-open
                raise
            except Exception as exc:
                logger.warning(
                    "baseline_deviation_scope_error",
                    event_type="baseline_deviation.scope_error",
                    scope=scope,
                    error=str(exc),
                )
                continue

            if result is None:
                # No deviations found for this scope
                continue

            finding_or_suppressed, deviation_count, suppressed_single = result

            deviations_detected += deviation_count

            if suppressed_single:
                deviations_suppressed_single_metric += 1
            elif finding_or_suppressed is not None:
                findings.append(finding_or_suppressed)
                logger.info(
                    "baseline_deviation_finding_emitted",
                    event_type="baseline_deviation.finding_emitted",
                    scope=scope,
                    deviating_metrics_count=deviation_count,
                    finding_id=finding_or_suppressed.finding_id,
                )

    except Exception as exc:
        logger.warning(
            "baseline_deviation_redis_unavailable",
            event_type="baseline_deviation.redis_unavailable",
            error=str(exc),
        )
        return BaselineDeviationStageOutput(
            findings=(),
            scopes_evaluated=0,
            deviations_detected=0,
            deviations_suppressed_single_metric=0,
            deviations_suppressed_dedup=0,
            evaluation_time=evaluation_time,
        )

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "baseline_deviation_stage_completed",
        event_type="baseline_deviation.stage_completed",
        scopes_evaluated=scopes_evaluated,
        findings_emitted=len(findings),
        suppressed_single_metric=deviations_suppressed_single_metric,
        suppressed_dedup=deviations_suppressed_dedup,
        duration_ms=round(elapsed_ms, 2),
    )

    return BaselineDeviationStageOutput(
        findings=tuple(findings),
        scopes_evaluated=scopes_evaluated,
        deviations_detected=deviations_detected,
        deviations_suppressed_single_metric=deviations_suppressed_single_metric,
        deviations_suppressed_dedup=deviations_suppressed_dedup,
        evaluation_time=evaluation_time,
    )


def _build_hand_coded_dedup_set(evidence_output: EvidenceStageOutput) -> frozenset[tuple[str, ...]]:
    """Return set of scopes where a hand-coded detector already fired this cycle."""
    return frozenset(
        finding.scope
        for finding in evidence_output.anomaly_result.findings
        if finding.anomaly_family in HAND_CODED_FAMILIES
    )


def _evaluate_scope(
    *,
    scope: tuple[str, ...],
    scope_metrics: dict[str, list[float]],
    baseline_client: SeasonalBaselineClient,
    dow: int,
    hour: int,
    evaluation_time: datetime,
    logger: structlog.BoundLogger,
) -> tuple[AnomalyFinding | None, int, bool] | None:
    """Evaluate a single scope for baseline deviations.

    Returns:
        None if no deviations were found at all.
        tuple(finding_or_None, deviation_count, suppressed_single) where:
          - finding_or_None: the AnomalyFinding if correlated, else None
          - deviation_count: number of deviating metrics
          - suppressed_single: True if suppressed due to single-metric threshold
    """
    # Aggregate: use max value per metric across multiple rows for the same scope
    current_values_by_metric = {
        metric_key: max(values)
        for metric_key, values in scope_metrics.items()
    }

    metric_keys = list(current_values_by_metric.keys())
    historical_by_metric = baseline_client.read_buckets_batch(scope, metric_keys, dow, hour)

    # Compute MAD z-score for each metric
    deviating_metrics: list[tuple[str, MADResult]] = []
    evaluated_metric_keys: list[str] = []

    for metric_key in sorted(metric_keys):  # sorted for determinism
        current_value = current_values_by_metric[metric_key]
        historical_values = historical_by_metric.get(metric_key, [])

        mad_result = compute_modified_z_score(historical_values, current_value)
        if mad_result is None:
            # Sparse data or zero-MAD — skip this metric
            continue

        evaluated_metric_keys.append(metric_key)

        if mad_result.is_deviation:
            deviating_metrics.append((metric_key, mad_result))

    if not deviating_metrics:
        return None

    deviation_count = len(deviating_metrics)

    # Correlation gate: require >= MIN_CORRELATED_DEVIATIONS deviating metrics
    if deviation_count < MIN_CORRELATED_DEVIATIONS:
        # Single-metric suppression — log at DEBUG per AC 3 / NFR-A3
        first_key = deviating_metrics[0][0]
        logger.debug(
            "baseline_deviation_suppressed_single_metric",
            event_type="baseline_deviation.suppressed_single_metric",
            scope=scope,
            metric_key=first_key,
            reason="SINGLE_METRIC_BELOW_THRESHOLD",
        )
        return (None, deviation_count, True)

    # Correlated deviation: emit finding
    finding = _build_baseline_deviation_finding(
        scope=scope,
        deviating_metrics=deviating_metrics,
        evaluated_metric_keys=tuple(evaluated_metric_keys),
        evaluation_time=evaluation_time,
    )
    return (finding, deviation_count, False)


def _build_baseline_deviation_finding(
    scope: tuple[str, ...],
    deviating_metrics: list[tuple[str, MADResult]],
    evaluated_metric_keys: tuple[str, ...],
    evaluation_time: datetime,
) -> AnomalyFinding:
    """Construct the AnomalyFinding from collected deviating metrics."""
    # Sort for determinism
    deviating_metrics_sorted = sorted(deviating_metrics, key=lambda x: x[0])
    scope_key = "|".join(scope)
    reason_codes = tuple(
        f"BASELINE_DEV:{mk}:{result.deviation_direction}"
        for mk, result in deviating_metrics_sorted
    )
    # Use first deviating metric (alphabetically) for baseline_context
    first_key, first_result = deviating_metrics_sorted[0]
    context = BaselineDeviationContext(
        metric_key=first_key,
        deviation_direction=first_result.deviation_direction,
        deviation_magnitude=first_result.deviation_magnitude,
        baseline_value=first_result.baseline_value,
        current_value=first_result.current_value,
        time_bucket=time_to_bucket(evaluation_time),
    )
    return AnomalyFinding(
        finding_id=f"BASELINE_DEVIATION:{scope_key}",
        anomaly_family="BASELINE_DEVIATION",
        scope=scope,
        severity="LOW",
        reason_codes=reason_codes,
        evidence_required=evaluated_metric_keys,
        is_primary=False,
        baseline_context=context,
    )
