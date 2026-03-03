from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.integrations.prometheus import PrometheusHTTPClient, build_metric_queries
from aiops_triage_pipeline.pipeline.stages.evidence import collect_prometheus_samples


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


