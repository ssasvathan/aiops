"""Evidence-stage helpers for scope key construction and sample normalization."""

import asyncio
from datetime import datetime
from typing import Any, Mapping
from urllib.error import URLError

from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusClientProtocol,
    normalize_labels,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.evidence import EvidenceRow, EvidenceStageOutput
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
                labels = {
                    k: v
                    for k, v in normalize_labels(sample["labels"]).items()
                    if k not in _IDENTITY_IGNORE_LABELS
                }
                rows.append(
                    EvidenceRow(
                        metric_key=metric_key,
                        value=float(sample["value"]),
                        labels=labels,
                        scope=build_evidence_scope_key(sample["labels"], metric_key=metric_key),
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


def collect_evidence_stage_output(
    samples_by_metric: Mapping[str, list[Mapping[str, Any]]],
) -> EvidenceStageOutput:
    """Collect normalized evidence rows and derive anomaly findings for downstream stages."""
    rows = collect_evidence_rows(samples_by_metric)
    anomaly_result = detect_anomaly_findings(rows)
    return EvidenceStageOutput(
        rows=tuple(rows),
        anomaly_result=anomaly_result,
        gate_findings_by_scope=build_gate_findings_by_scope(anomaly_result),
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
    logger = get_logger("pipeline.stages.evidence")
    collected: dict[str, list[dict[str, Any]]] = {}

    for metric_key, query in metric_queries.items():
        try:
            samples = await asyncio.to_thread(
                client.query_instant, query.metric_name, evaluation_time
            )
            collected[metric_key] = list(samples)
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning(
                "prometheus_collection_missed_window",
                event_type="evidence.prometheus_collection_warning",
                metric_key=metric_key,
                metric_name=getattr(query, "metric_name", metric_key),
                evaluation_time=evaluation_time.isoformat(),
                reason=str(exc),
            )
            collected[metric_key] = []

    return collected
