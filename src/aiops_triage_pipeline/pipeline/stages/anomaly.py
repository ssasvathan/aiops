"""Anomaly detection stage based on normalized Stage 1 evidence rows."""

import math
from collections import defaultdict
from datetime import datetime
from typing import Mapping

from aiops_triage_pipeline.cache.findings_cache import (
    FindingsCacheClientProtocol,
    get_or_compute_interval_findings,
)
from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.anomaly import (
    AnomalyDetectionResult,
    AnomalyFinding,
)
from aiops_triage_pipeline.models.evidence import EvidenceRow

# Detector thresholds centralized for deterministic tuning and test coverage.
_LAG_BUILDUP_MIN_LAG = 100.0
_LAG_BUILDUP_MIN_GROWTH = 25.0
_LAG_BUILDUP_MAX_OFFSET_PROGRESS = 10.0
_THROUGHPUT_MIN_MESSAGES_PER_SEC = 1000.0
_THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC = 100.0
_THROUGHPUT_FAILURE_RATIO_MIN = 0.05
_VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC = 1.0
_VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC = 50.0
_VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC = 150.0


def detect_anomaly_findings(
    rows: list[EvidenceRow],
    *,
    findings_cache_client: FindingsCacheClientProtocol | None = None,
    redis_ttl_policy: RedisTtlPolicyV1 | None = None,
    evaluation_time: datetime | None = None,
    baseline_values_by_scope: Mapping[tuple[str, ...], Mapping[str, float]] | None = None,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> AnomalyDetectionResult:
    """Detect supported anomaly families from normalized evidence rows."""
    cache_args_complete = (
        findings_cache_client is not None
        and redis_ttl_policy is not None
        and evaluation_time is not None
    )
    cache_args_partial = (
        findings_cache_client is not None
        or redis_ttl_policy is not None
        or evaluation_time is not None
    ) and not cache_args_complete
    if cache_args_partial:
        get_logger("pipeline.stages.anomaly").warning(
            "findings_cache_configuration_incomplete",
            event_type="cache.findings_cache_configuration_warning",
            has_findings_cache_client=findings_cache_client is not None,
            has_redis_ttl_policy=redis_ttl_policy is not None,
            has_evaluation_time=evaluation_time is not None,
        )

    metrics_by_scope: dict[tuple[str, ...], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        metrics_by_scope[row.scope][row.metric_key].append(row.value)

    findings: list[AnomalyFinding] = []
    for scope in sorted(metrics_by_scope):
        scope_metrics = metrics_by_scope[scope]
        if cache_args_complete:
            scope_findings = get_or_compute_interval_findings(
                redis_client=findings_cache_client,
                scope=scope,
                evaluation_time=evaluation_time,
                redis_ttl_policy=redis_ttl_policy,
                compute_findings=lambda: _compute_scope_findings(
                    scope,
                    scope_metrics,
                    baseline_values_by_scope.get(scope) if baseline_values_by_scope else None,
                    anomaly_detection_policy=anomaly_detection_policy,
                ),
            )
        else:
            scope_findings = _compute_scope_findings(
                scope,
                scope_metrics,
                baseline_values_by_scope.get(scope) if baseline_values_by_scope else None,
                anomaly_detection_policy=anomaly_detection_policy,
            )
        findings.extend(scope_findings)

    finding_tuple = tuple(findings)
    # findings_by_scope is auto-derived from findings by AnomalyDetectionResult's model_validator.
    return AnomalyDetectionResult(findings=finding_tuple)


def _compute_scope_findings(
    scope: tuple[str, ...],
    scope_metrics: dict[str, list[float]],
    baseline_values_by_metric: Mapping[str, float] | None = None,
    *,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> tuple[AnomalyFinding, ...]:
    scope_findings: list[AnomalyFinding] = []

    lag_finding = _detect_consumer_lag_buildup(
        scope, scope_metrics, anomaly_detection_policy=anomaly_detection_policy
    )
    if lag_finding is not None:
        scope_findings.append(lag_finding)

    throughput_finding = _detect_throughput_constrained_proxy(
        scope, scope_metrics, anomaly_detection_policy=anomaly_detection_policy
    )
    if throughput_finding is not None:
        scope_findings.append(throughput_finding)

    volume_drop_finding = _detect_volume_drop(
        scope,
        scope_metrics,
        baseline_messages_in=(
            baseline_values_by_metric.get("topic_messages_in_per_sec")
            if baseline_values_by_metric
            else None
        ),
        anomaly_detection_policy=anomaly_detection_policy,
    )
    if volume_drop_finding is not None:
        scope_findings.append(volume_drop_finding)

    return tuple(scope_findings)


def build_gate_findings_by_scope(
    result: AnomalyDetectionResult,
) -> dict[tuple[str, ...], tuple[Finding, ...]]:
    """Build GateInput-compatible finding payloads grouped by normalized scope."""
    return {
        scope: tuple(_to_gate_finding(finding) for finding in scope_findings)
        for scope, scope_findings in result.findings_by_scope.items()
    }


def _detect_consumer_lag_buildup(
    scope: tuple[str, ...],
    scope_metrics: dict[str, list[float]],
    *,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> AnomalyFinding | None:
    lag_values = scope_metrics.get("consumer_group_lag")
    offset_values = scope_metrics.get("consumer_group_offset")
    if not lag_values or not offset_values:
        return None

    min_lag = (
        anomaly_detection_policy.lag_buildup_min_lag
        if anomaly_detection_policy
        else _LAG_BUILDUP_MIN_LAG
    )
    min_growth = (
        anomaly_detection_policy.lag_buildup_min_growth
        if anomaly_detection_policy
        else _LAG_BUILDUP_MIN_GROWTH
    )
    max_offset_progress = (
        anomaly_detection_policy.lag_buildup_max_offset_progress
        if anomaly_detection_policy
        else _LAG_BUILDUP_MAX_OFFSET_PROGRESS
    )

    lag_end = max(lag_values)
    # For multi-sample scopes (real Kafka: per-partition series collapse to one scope after
    # partition label is stripped), last-minus-first preserves temporal direction so that
    # decreasing lag does not trigger detection.
    # For single-sample scopes (e.g. harness without per-partition labels), treat the observed
    # lag magnitude as the growth indicator — a high single observation implies growth from zero.
    if len(lag_values) >= 2:
        lag_growth = lag_values[-1] - lag_values[0]
    else:
        lag_growth = lag_end

    # Use max-min spread for offset progress to be independent of sample list ordering.
    offset_progress = max(offset_values) - min(offset_values)
    if lag_end < min_lag:
        return None
    if lag_growth < min_growth:
        return None
    if offset_progress > max_offset_progress:
        return None

    scope_key = "|".join(scope)
    return AnomalyFinding(
        finding_id=f"CONSUMER_LAG:{scope_key}",
        anomaly_family="CONSUMER_LAG",
        scope=scope,
        severity="HIGH",
        reason_codes=("LAG_BUILDUP_DETECTED", "LAG_HIGH", "OFFSET_PROGRESS_LOW"),
        evidence_required=("consumer_group_lag", "consumer_group_offset"),
        is_primary=True,
    )


def _to_gate_finding(finding: AnomalyFinding) -> Finding:
    return Finding(
        finding_id=finding.finding_id,
        name=finding.anomaly_family.lower(),
        is_anomalous=True,
        evidence_required=finding.evidence_required,
        allowed_non_present_statuses_by_evidence=finding.allowed_non_present_statuses_by_evidence,
        is_primary=finding.is_primary,
        severity=finding.severity,
        reason_codes=finding.reason_codes,
    )


def _detect_throughput_constrained_proxy(
    scope: tuple[str, ...],
    scope_metrics: dict[str, list[float]],
    *,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> AnomalyFinding | None:
    throughput_values = scope_metrics.get("topic_messages_in_per_sec")
    total_produce_values = scope_metrics.get("total_produce_requests_per_sec")
    failed_produce_values = scope_metrics.get("failed_produce_requests_per_sec")
    if not throughput_values or not total_produce_values or not failed_produce_values:
        return None

    min_messages_per_sec = (
        anomaly_detection_policy.throughput_min_messages_per_sec
        if anomaly_detection_policy
        else _THROUGHPUT_MIN_MESSAGES_PER_SEC
    )
    min_total_produce_per_sec = (
        anomaly_detection_policy.throughput_min_total_produce_requests_per_sec
        if anomaly_detection_policy
        else _THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC
    )
    failure_ratio_min = (
        anomaly_detection_policy.throughput_failure_ratio_min
        if anomaly_detection_policy
        else _THROUGHPUT_FAILURE_RATIO_MIN
    )

    throughput = max(throughput_values)
    total_produce = max(total_produce_values)
    failed_produce = max(failed_produce_values)
    if throughput < min_messages_per_sec:
        return None
    if total_produce < min_total_produce_per_sec:
        return None
    if total_produce <= 0:
        return None

    failure_ratio = failed_produce / total_produce
    if failure_ratio < failure_ratio_min:
        return None

    scope_key = "|".join(scope)
    return AnomalyFinding(
        finding_id=f"THROUGHPUT_CONSTRAINED_PROXY:{scope_key}",
        anomaly_family="THROUGHPUT_CONSTRAINED_PROXY",
        scope=scope,
        severity="HIGH",
        reason_codes=("HIGH_THROUGHPUT", "PRODUCE_FAILURE_RATIO_HIGH"),
        evidence_required=(
            "topic_messages_in_per_sec",
            "total_produce_requests_per_sec",
            "failed_produce_requests_per_sec",
        ),
        is_primary=True,
    )


def _detect_volume_drop(
    scope: tuple[str, ...],
    scope_metrics: dict[str, list[float]],
    *,
    baseline_messages_in: float | None = None,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> AnomalyFinding | None:
    messages_in_values = scope_metrics.get("topic_messages_in_per_sec")
    total_produce_values = scope_metrics.get("total_produce_requests_per_sec")
    if not messages_in_values or not total_produce_values:
        return None

    max_current_messages_in = (
        anomaly_detection_policy.volume_drop_max_current_messages_in_per_sec
        if anomaly_detection_policy
        else _VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC
    )
    min_baseline_messages_in = (
        anomaly_detection_policy.volume_drop_min_baseline_messages_in_per_sec
        if anomaly_detection_policy
        else _VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC
    )
    min_expected_requests = (
        anomaly_detection_policy.volume_drop_min_expected_requests_per_sec
        if anomaly_detection_policy
        else _VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC
    )

    # Use max as baseline and min as current to be independent of sample list ordering.
    # Detects: peak throughput is high but the lowest observed value for the scope is near zero,
    # indicating a drop regardless of whether samples are temporal or cross-broker.
    baseline_from_current = max(messages_in_values)
    if (
        baseline_messages_in is None
        or not math.isfinite(baseline_messages_in)
        or baseline_messages_in <= 0
    ):
        baseline_messages_in = baseline_from_current
    else:
        # Never let an unexpectedly low cached value reduce the in-cycle baseline.
        baseline_messages_in = max(baseline_messages_in, baseline_from_current)
    current_messages_in = min(messages_in_values)
    expected_requests = max(total_produce_values)
    if baseline_messages_in < min_baseline_messages_in:
        return None
    if expected_requests < min_expected_requests:
        return None
    if current_messages_in > max_current_messages_in:
        return None

    scope_key = "|".join(scope)
    return AnomalyFinding(
        finding_id=f"VOLUME_DROP:{scope_key}",
        anomaly_family="VOLUME_DROP",
        scope=scope,
        severity="MEDIUM",
        reason_codes=("EXPECTED_INGRESS_BUT_LOW_TRAFFIC", "VOLUME_DROP_VS_BASELINE"),
        evidence_required=("topic_messages_in_per_sec", "total_produce_requests_per_sec"),
        is_primary=True,
    )
