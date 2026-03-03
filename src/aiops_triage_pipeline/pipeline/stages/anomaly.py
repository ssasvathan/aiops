"""Anomaly detection stage based on normalized Stage 1 evidence rows."""

from collections import defaultdict

from aiops_triage_pipeline.contracts.gate_input import Finding
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


def detect_anomaly_findings(rows: list[EvidenceRow]) -> AnomalyDetectionResult:
    """Detect supported anomaly families from normalized evidence rows."""
    metrics_by_scope: dict[tuple[str, ...], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        metrics_by_scope[row.scope][row.metric_key].append(row.value)

    findings: list[AnomalyFinding] = []
    for scope in sorted(metrics_by_scope):
        scope_metrics = metrics_by_scope[scope]

        lag_finding = _detect_consumer_lag_buildup(scope, scope_metrics)
        if lag_finding is not None:
            findings.append(lag_finding)

        throughput_finding = _detect_throughput_constrained_proxy(scope, scope_metrics)
        if throughput_finding is not None:
            findings.append(throughput_finding)

        volume_drop_finding = _detect_volume_drop(scope, scope_metrics)
        if volume_drop_finding is not None:
            findings.append(volume_drop_finding)

    finding_tuple = tuple(findings)
    # findings_by_scope is auto-derived from findings by AnomalyDetectionResult's model_validator.
    return AnomalyDetectionResult(findings=finding_tuple)


def build_gate_findings_by_scope(
    result: AnomalyDetectionResult,
) -> dict[tuple[str, ...], tuple[Finding, ...]]:
    """Build GateInput-compatible finding payloads grouped by normalized scope."""
    return {
        scope: tuple(_to_gate_finding(finding) for finding in scope_findings)
        for scope, scope_findings in result.findings_by_scope.items()
    }


def _detect_consumer_lag_buildup(
    scope: tuple[str, ...], scope_metrics: dict[str, list[float]]
) -> AnomalyFinding | None:
    lag_values = scope_metrics.get("consumer_group_lag")
    offset_values = scope_metrics.get("consumer_group_offset")
    if not lag_values or not offset_values:
        return None
    if len(lag_values) < 2 or len(offset_values) < 2:
        return None

    # lag_growth is computed as last-minus-first to preserve temporal direction:
    # negative growth (decreasing lag) must not trigger detection.
    lag_growth = lag_values[-1] - lag_values[0]
    # Use max-min spread for offset progress to be independent of sample list ordering.
    offset_progress = max(offset_values) - min(offset_values)
    lag_end = max(lag_values)
    if lag_end < _LAG_BUILDUP_MIN_LAG:
        return None
    if lag_growth < _LAG_BUILDUP_MIN_GROWTH:
        return None
    if offset_progress > _LAG_BUILDUP_MAX_OFFSET_PROGRESS:
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
        is_primary=finding.is_primary,
        severity=finding.severity,
        reason_codes=finding.reason_codes,
    )


def _detect_throughput_constrained_proxy(
    scope: tuple[str, ...], scope_metrics: dict[str, list[float]]
) -> AnomalyFinding | None:
    throughput_values = scope_metrics.get("topic_messages_in_per_sec")
    total_produce_values = scope_metrics.get("total_produce_requests_per_sec")
    failed_produce_values = scope_metrics.get("failed_produce_requests_per_sec")
    if not throughput_values or not total_produce_values or not failed_produce_values:
        return None

    throughput = max(throughput_values)
    total_produce = max(total_produce_values)
    failed_produce = max(failed_produce_values)
    if throughput < _THROUGHPUT_MIN_MESSAGES_PER_SEC:
        return None
    if total_produce < _THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC:
        return None
    if total_produce <= 0:
        return None

    failure_ratio = failed_produce / total_produce
    if failure_ratio < _THROUGHPUT_FAILURE_RATIO_MIN:
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
    scope: tuple[str, ...], scope_metrics: dict[str, list[float]]
) -> AnomalyFinding | None:
    messages_in_values = scope_metrics.get("topic_messages_in_per_sec")
    total_produce_values = scope_metrics.get("total_produce_requests_per_sec")
    if not messages_in_values or not total_produce_values:
        return None

    # Use max as baseline and min as current to be independent of sample list ordering.
    # Detects: peak throughput is high but the lowest observed value for the scope is near zero,
    # indicating a drop regardless of whether samples are temporal or cross-broker.
    baseline_messages_in = max(messages_in_values)
    current_messages_in = min(messages_in_values)
    expected_requests = max(total_produce_values)
    if baseline_messages_in < _VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC:
        return None
    if expected_requests < _VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC:
        return None
    if current_messages_in > _VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC:
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
