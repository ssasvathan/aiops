"""Evidence-stage helpers for scope key construction and sample normalization."""

import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from urllib.error import URLError

from aiops_triage_pipeline.cache.findings_cache import FindingsCacheClientProtocol
from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1
from aiops_triage_pipeline.contracts.enums import Action, EvidenceStatus
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.health.metrics import (
    record_evidence_unknown_rate,
    record_prometheus_scrape_result,
)
from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusClientProtocol,
    normalize_labels,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.events import TelemetryDegradedEvent
from aiops_triage_pipeline.models.evidence import EvidenceRow, EvidenceStageOutput
from aiops_triage_pipeline.pipeline.baseline_store import (
    BaselineStoreClientProtocol,
    load_metric_baselines,
    persist_metric_baselines,
)
from aiops_triage_pipeline.pipeline.stages.anomaly import (
    build_gate_findings_by_scope,
    detect_anomaly_findings,
)

_LAG_METRIC_KEYS = frozenset({"consumer_group_lag", "consumer_group_offset"})

# Labels excluded from identity and evidence storage per prometheus-metrics-contract-v1
# identity.ignore_labels_for_identity
_IDENTITY_IGNORE_LABELS = frozenset(
    {"instance", "job", "nodes_group", "client_id", "consumer_id", "member_host", "partition"}
)
_PROMETHEUS_SOURCE_FAILURES = (URLError, TimeoutError, OSError)


@dataclass(frozen=True)
class PrometheusCollectionDiagnostics:
    """Collection result with source-outage diagnostics for one scheduler cycle."""

    samples_by_metric: dict[str, list[dict[str, Any]]]
    failed_metric_keys: tuple[str, ...]
    is_total_outage: bool
    outage_reason: str | None


def build_evidence_scope_key(labels: Mapping[str, str], metric_key: str) -> tuple[str, ...]:
    """Build evidence identity scope key by metric family requirements.

    Raises ValueError if required labels are absent.
    """
    normalized = normalize_labels(labels)  # raises ValueError if cluster_name missing
    env = normalized.get("env")
    if env is None:
        raise ValueError(f"Required label 'env' missing for metric '{metric_key}'")
    cluster_id = normalized["cluster_id"]

    if metric_key in _LAG_METRIC_KEYS:
        group = normalized.get("group")
        topic = normalized.get("topic")
        if group is None or topic is None:
            raise ValueError(
                f"Required labels 'group' and 'topic' missing for lag metric '{metric_key}'"
            )
        return (env, cluster_id, group, topic)

    topic = normalized.get("topic")
    if topic is None:
        raise ValueError(f"Required label 'topic' missing for metric '{metric_key}'")
    return (env, cluster_id, topic)


def collect_evidence_rows(
    samples_by_metric: Mapping[str, list[Mapping[str, Any]]],
) -> list[EvidenceRow]:
    """Normalize raw Prometheus samples into evidence rows with deterministic scopes."""
    logger = get_logger("pipeline.stages.evidence")
    rows: list[EvidenceRow] = []
    for metric_key, samples in samples_by_metric.items():
        for sample in samples:
            try:
                # Normalize once and reuse for both the stored labels dict and scope key
                # to avoid a redundant dict allocation per sample.
                normalized_raw = normalize_labels(sample["labels"])
                labels = {
                    k: v for k, v in normalized_raw.items() if k not in _IDENTITY_IGNORE_LABELS
                }
                rows.append(
                    EvidenceRow(
                        metric_key=metric_key,
                        value=float(sample["value"]),
                        labels=labels,
                        scope=build_evidence_scope_key(normalized_raw, metric_key=metric_key),
                    )
                )
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "evidence_row_normalization_failed",
                    event_type="evidence.normalization_warning",
                    metric_key=metric_key,
                    reason=str(exc),
                )
    return rows


def build_evidence_status_map_by_scope(
    *,
    metric_keys: Sequence[str],
    rows: Sequence[EvidenceRow],
) -> dict[tuple[str, ...], dict[str, EvidenceStatus]]:
    """Build per-scope evidence status maps with UNKNOWN for missing metric series."""
    present_metrics_by_scope: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for row in rows:
        present_metrics_by_scope[row.scope].add(row.metric_key)

    evidence_status_map_by_scope: dict[tuple[str, ...], dict[str, EvidenceStatus]] = {}
    for scope in sorted(present_metrics_by_scope):
        present_metric_keys = present_metrics_by_scope[scope]
        evidence_status_map_by_scope[scope] = {
            metric_key: (
                EvidenceStatus.PRESENT
                if metric_key in present_metric_keys
                else EvidenceStatus.UNKNOWN
            )
            for metric_key in metric_keys
        }

    return evidence_status_map_by_scope


def collect_evidence_stage_output(
    samples_by_metric: Mapping[str, list[Mapping[str, Any]]],
    *,
    findings_cache_client: FindingsCacheClientProtocol | None = None,
    baseline_cache_client: BaselineStoreClientProtocol | None = None,
    baseline_source: str = "prometheus",
    redis_ttl_policy: RedisTtlPolicyV1 | None = None,
    evaluation_time: datetime | None = None,
    telemetry_degraded_active: bool = False,
    telemetry_degraded_events: Sequence[TelemetryDegradedEvent] = (),
    max_safe_action: Action | None = None,
    anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None,
) -> EvidenceStageOutput:
    """Collect normalized evidence rows and derive anomaly findings for downstream stages."""
    rows = collect_evidence_rows(samples_by_metric)
    baseline_values_by_scope: Mapping[tuple[str, ...], Mapping[str, float]] | None = None
    if baseline_cache_client is not None and redis_ttl_policy is not None:
        baseline_values_by_scope = load_metric_baselines(
            redis_client=baseline_cache_client,
            source=baseline_source,
            scope_metric_pairs=_scope_metric_pairs_from_rows(rows),
        )
    anomaly_result = detect_anomaly_findings(
        rows,
        findings_cache_client=findings_cache_client,
        redis_ttl_policy=redis_ttl_policy,
        evaluation_time=evaluation_time,
        baseline_values_by_scope=baseline_values_by_scope,
        anomaly_detection_policy=anomaly_detection_policy,
    )
    if baseline_cache_client is not None and redis_ttl_policy is not None:
        persist_metric_baselines(
            redis_client=baseline_cache_client,
            source=baseline_source,
            baselines_by_scope_metric=_compute_baselines_from_rows(rows),
            redis_ttl_policy=redis_ttl_policy,
            computed_at=evaluation_time,
        )
    evidence_status_map_by_scope = build_evidence_status_map_by_scope(
        metric_keys=tuple(samples_by_metric.keys()),
        rows=rows,
    )
    total_scope_count = len(evidence_status_map_by_scope)
    for metric_key in samples_by_metric:
        unknown_count = sum(
            1
            for status_by_metric in evidence_status_map_by_scope.values()
            if status_by_metric.get(metric_key) == EvidenceStatus.UNKNOWN
        )
        record_evidence_unknown_rate(
            metric_key=metric_key,
            unknown_count=unknown_count,
            total_count=total_scope_count,
        )
    return EvidenceStageOutput(
        rows=tuple(rows),
        anomaly_result=anomaly_result,
        gate_findings_by_scope=build_gate_findings_by_scope(anomaly_result),
        evidence_status_map_by_scope=evidence_status_map_by_scope,
        telemetry_degraded_active=telemetry_degraded_active,
        telemetry_degraded_events=tuple(telemetry_degraded_events),
        max_safe_action=max_safe_action,
    )


async def collect_prometheus_samples(
    *,
    client: PrometheusClientProtocol,
    metric_queries: Mapping[str, MetricQueryDefinition],
    evaluation_time: datetime,
) -> dict[str, list[dict[str, Any]]]:
    """Collect metric samples from Prometheus with warning logs on missed windows/errors.

    Uses asyncio.to_thread for each blocking HTTP call to avoid stalling the event loop
    on the hot-path evaluation cadence.
    """
    diagnostics = await collect_prometheus_samples_with_diagnostics(
        client=client,
        metric_queries=metric_queries,
        evaluation_time=evaluation_time,
    )
    return diagnostics.samples_by_metric


async def collect_prometheus_samples_with_diagnostics(
    *,
    client: PrometheusClientProtocol,
    metric_queries: Mapping[str, MetricQueryDefinition],
    evaluation_time: datetime,
) -> PrometheusCollectionDiagnostics:
    """Collect samples and classify whether a full Prometheus source outage occurred."""
    logger = get_logger("pipeline.stages.evidence")
    collected: dict[str, list[dict[str, Any]]] = {}
    failed_metric_keys: list[str] = []
    failure_reasons_by_metric: dict[str, str] = {}

    for metric_key, query in metric_queries.items():
        try:
            samples = await asyncio.to_thread(
                client.query_instant, query.metric_name, evaluation_time
            )
            collected[metric_key] = list(samples)
            record_prometheus_scrape_result(metric_key=metric_key, success=True)
        except _PROMETHEUS_SOURCE_FAILURES as exc:
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "prometheus_collection_missed_window",
                event_type="evidence.prometheus_collection_warning",
                metric_key=metric_key,
                metric_name=getattr(query, "metric_name", metric_key),
                evaluation_time=evaluation_time.isoformat(),
                reason=reason,
            )
            failed_metric_keys.append(metric_key)
            failure_reasons_by_metric[metric_key] = reason
            collected[metric_key] = []
            record_prometheus_scrape_result(metric_key=metric_key, success=False)
        except ValueError as exc:
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "prometheus_collection_missed_window",
                event_type="evidence.prometheus_collection_warning",
                metric_key=metric_key,
                metric_name=getattr(query, "metric_name", metric_key),
                evaluation_time=evaluation_time.isoformat(),
                reason=reason,
            )
            # Only treat explicit non-success API responses as outage candidates.
            if _is_prometheus_non_success_api_error(exc):
                failed_metric_keys.append(metric_key)
                failure_reasons_by_metric[metric_key] = reason
                record_prometheus_scrape_result(metric_key=metric_key, success=False)
            else:
                record_prometheus_scrape_result(metric_key=metric_key, success=True)
            collected[metric_key] = []

    is_total_outage = bool(metric_queries) and len(failed_metric_keys) == len(metric_queries)
    outage_reason: str | None = None

    if is_total_outage:
        first_failed_metric_key = failed_metric_keys[0]
        first_reason = failure_reasons_by_metric[first_failed_metric_key]
        outage_reason = (
            f"Prometheus source unavailable across all {len(metric_queries)} configured metrics; "
            f"first failure [{first_failed_metric_key}]: {first_reason}"
        )
        logger.warning(
            "prometheus_total_source_outage_detected",
            event_type="evidence.prometheus_total_outage",
            evaluation_time=evaluation_time.isoformat(),
            failed_metric_count=len(failed_metric_keys),
            total_metric_count=len(metric_queries),
            reason=outage_reason,
        )

    return PrometheusCollectionDiagnostics(
        samples_by_metric=collected,
        failed_metric_keys=tuple(failed_metric_keys),
        is_total_outage=is_total_outage,
        outage_reason=outage_reason,
    )


def _is_prometheus_non_success_api_error(exc: ValueError) -> bool:
    message = str(exc)
    return message.startswith("Prometheus query failed for ")


def _scope_metric_pairs_from_rows(rows: Sequence[EvidenceRow]) -> list[tuple[tuple[str, ...], str]]:
    return sorted({(row.scope, row.metric_key) for row in rows})


def _compute_baselines_from_rows(
    rows: Sequence[EvidenceRow],
) -> dict[tuple[str, ...], dict[str, float]]:
    values_by_scope_metric: dict[tuple[str, ...], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        if math.isfinite(row.value):
            values_by_scope_metric[row.scope][row.metric_key].append(row.value)

    baselines_by_scope_metric: dict[tuple[str, ...], dict[str, float]] = {}
    for scope, values_by_metric in sorted(values_by_scope_metric.items()):
        baseline_by_metric: dict[str, float] = {}
        for metric_key, values in sorted(values_by_metric.items()):
            if not values:
                continue
            baseline_by_metric[metric_key] = max(values)
        if baseline_by_metric:
            baselines_by_scope_metric[scope] = baseline_by_metric
    return baselines_by_scope_metric
