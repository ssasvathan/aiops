from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.integrations.prometheus import PrometheusHTTPClient, build_metric_queries
from aiops_triage_pipeline.pipeline.stages.evidence import (
    collect_evidence_stage_output,
    collect_prometheus_samples,
)


@pytest.mark.integration
async def test_evidence_collection_path_reads_from_local_prometheus() -> None:
    client = PrometheusHTTPClient(base_url="http://localhost:9090")
    queries = build_metric_queries()

    try:
        collected = await collect_prometheus_samples(
            client=client,
            metric_queries={
                "topic_messages_in_per_sec": queries["topic_messages_in_per_sec"],
                "consumer_group_lag": queries["consumer_group_lag"],
            },
            evaluation_time=datetime.now(tz=UTC),
        )
    except (URLError, TimeoutError, ConnectionError) as exc:
        pytest.skip(f"Local Prometheus unavailable at http://localhost:9090: {exc}")

    assert set(collected.keys()) == {"topic_messages_in_per_sec", "consumer_group_lag"}
    assert all(isinstance(v, list) for v in collected.values())


@pytest.mark.integration
def test_evidence_stage_output_detects_harness_like_patterns() -> None:
    samples = {
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 120.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 180.0,
            }
        ],
        "consumer_group_offset": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 2.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 8.0,
            }
        ],
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 1400.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 180.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 0.4,
            },
        ],
        "total_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 200.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 220.0,
            },
        ],
        "failed_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 24.0,
            }
        ],
    }

    output = collect_evidence_stage_output(samples)
    families = {finding.anomaly_family for finding in output.anomaly_result.findings}

    assert "CONSUMER_LAG" in families
    assert "THROUGHPUT_CONSTRAINED_PROXY" in families
    assert "VOLUME_DROP" in families
    assert ("prod", "cluster-a", "payments-worker", "payments") in output.gate_findings_by_scope
    assert ("prod", "cluster-a", "orders") in output.gate_findings_by_scope
    assert ("prod", "cluster-a", "inventory") in output.gate_findings_by_scope
