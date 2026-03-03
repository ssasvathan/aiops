from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.integrations.prometheus import (
    PrometheusHTTPClient,
    build_metric_queries,
)


@pytest.mark.integration
def test_local_prometheus_query_path_smoke() -> None:
    queries = build_metric_queries()
    metric = queries["topic_messages_in_per_sec"].metric_name
    client = PrometheusHTTPClient(base_url="http://localhost:9090")

    try:
        samples = client.query_instant(metric, at_time=datetime.now(tz=UTC))
    except (URLError, TimeoutError, ConnectionError) as exc:
        pytest.skip(f"Local Prometheus unavailable at http://localhost:9090: {exc}")

    assert isinstance(samples, list)
    if samples:
        assert "labels" in samples[0]
        assert "value" in samples[0]
