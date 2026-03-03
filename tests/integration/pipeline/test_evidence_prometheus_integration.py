from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.integrations.prometheus import PrometheusHTTPClient, build_metric_queries
from aiops_triage_pipeline.pipeline.stages.evidence import (
    collect_evidence_stage_output,
    collect_prometheus_samples,
)
from aiops_triage_pipeline.pipeline.stages.peak import collect_peak_stage_output


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


def test_stage1_output_feeds_stage2_peak_classification_shape() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 18.0,
            }
        ],
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "consumer-a",
                    "topic": "orders",
                },
                "value": 120.0,
            }
        ],
    }
    evidence_output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "orders")

    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    assert scope in peak_output.classifications_by_scope
    assert scope in peak_output.peak_context_by_scope
    # value=18.0, history=[1..20]: near_peak_threshold=p90=18, peak_threshold=p95=19
    # 18 >= near_peak_threshold(18) and < peak_threshold(19) → NEAR_PEAK
    assert peak_output.peak_context_by_scope[scope].classification == "NEAR_PEAK"

