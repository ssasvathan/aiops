import io
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from aiops_triage_pipeline.integrations.prometheus import (
    DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH,
    PrometheusHTTPClient,
    build_metric_queries,
    normalize_labels,
)


def test_build_metric_queries_uses_only_canonical_names() -> None:
    queries = build_metric_queries(DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH)

    assert "topic_messages_in_per_sec" in queries
    assert queries["topic_messages_in_per_sec"].metric_name == (
        "kafka_server_brokertopicmetrics_messagesinpersec"
    )
    assert queries["consumer_group_lag"].metric_name == "kafka_consumergroup_group_lag"
    assert all(defn.metric_name for defn in queries.values())


def test_build_metric_queries_covers_all_contract_metrics() -> None:
    """Every metric key in the contract must appear in the query map with matching key."""
    from aiops_triage_pipeline.integrations.prometheus import load_prometheus_metrics_contract

    contract = load_prometheus_metrics_contract(DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH)
    queries = build_metric_queries(DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH)

    assert set(queries.keys()) == set(contract.metrics.keys())
    for key, defn in queries.items():
        assert defn.metric_key == key
        assert defn.metric_name == contract.metrics[key].canonical


def test_normalize_labels_maps_cluster_name_to_cluster_id_exactly() -> None:
    labels = {"env": "dev", "cluster_name": "alpha-cluster", "topic": "orders"}

    normalized = normalize_labels(labels)

    assert normalized["cluster_id"] == "alpha-cluster"
    assert normalized["cluster_name"] == "alpha-cluster"


def test_normalize_labels_rejects_missing_cluster_name() -> None:
    with pytest.raises(ValueError, match="cluster_name"):
        normalize_labels({"env": "dev", "topic": "orders"})


# ---------------------------------------------------------------------------
# PrometheusHTTPClient.query_range() tests
# ---------------------------------------------------------------------------


def _make_matrix_response(results: list[dict]) -> io.BytesIO:
    payload = {
        "status": "success",
        "data": {"resultType": "matrix", "result": results},
    }
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def _matrix_item(labels: dict, values: list) -> dict:
    return {"metric": labels, "values": values}


def test_query_range_returns_matrix_results() -> None:
    raw = _make_matrix_response([
        _matrix_item(
            {"env": "dev", "cluster_name": "alpha", "topic": "orders"},
            [[1700000000.0, "42.5"], [1700000300.0, "55.0"]],
        ),
    ])
    client = PrometheusHTTPClient()
    with patch("aiops_triage_pipeline.integrations.prometheus.urlopen", return_value=raw):
        records = client.query_range(
            "kafka_server_brokertopicmetrics_messagesinpersec",
            datetime(2026, 4, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
            step_seconds=300,
        )

    assert len(records) == 1
    record = records[0]
    assert record["labels"] == {"env": "dev", "cluster_name": "alpha", "topic": "orders"}
    values = record["values"]
    assert len(values) == 2
    assert values[0] == (1700000000.0, 42.5)
    assert values[1] == (1700000300.0, 55.0)


def test_query_range_filters_nan_inf_values() -> None:
    raw = _make_matrix_response([
        _matrix_item(
            {"cluster_name": "alpha"},
            [
                [1000.0, "10.0"],
                [1300.0, "NaN"],
                [1600.0, "Inf"],
                [1900.0, "-Inf"],
                [2200.0, "20.0"],
            ],
        ),
    ])
    _start = datetime(2026, 1, 1, tzinfo=UTC)
    _end = datetime(2026, 1, 2, tzinfo=UTC)
    client = PrometheusHTTPClient()
    with patch("aiops_triage_pipeline.integrations.prometheus.urlopen", return_value=raw):
        records = client.query_range("m", _start, _end, 300)

    assert len(records) == 1
    values = records[0]["values"]
    # Only finite values survive
    assert values == [(1000.0, 10.0), (2200.0, 20.0)]


def test_query_range_raises_on_non_success_status() -> None:
    raw = io.BytesIO(json.dumps({"status": "error", "error": "bad request"}).encode())
    _start = datetime(2026, 1, 1, tzinfo=UTC)
    _end = datetime(2026, 1, 2, tzinfo=UTC)
    client = PrometheusHTTPClient()
    with patch("aiops_triage_pipeline.integrations.prometheus.urlopen", return_value=raw):
        with pytest.raises(ValueError, match="range query failed"):
            client.query_range("m", _start, _end, 300)


def test_query_range_raises_on_non_matrix_result_type() -> None:
    raw = io.BytesIO(json.dumps({
        "status": "success",
        "data": {"resultType": "vector", "result": []},
    }).encode())
    _start = datetime(2026, 1, 1, tzinfo=UTC)
    _end = datetime(2026, 1, 2, tzinfo=UTC)
    client = PrometheusHTTPClient()
    with patch("aiops_triage_pipeline.integrations.prometheus.urlopen", return_value=raw):
        with pytest.raises(ValueError, match="matrix"):
            client.query_range("m", _start, _end, 300)


def test_query_range_builds_correct_url_params() -> None:
    from urllib.parse import parse_qs, urlparse

    captured_url: list[str] = []

    def fake_urlopen(url, *, timeout):
        captured_url.append(url)
        return _make_matrix_response([])

    client = PrometheusHTTPClient(base_url="http://prom:9090")
    start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 4, 2, 0, 0, 0, tzinfo=UTC)
    with patch("aiops_triage_pipeline.integrations.prometheus.urlopen", side_effect=fake_urlopen):
        client.query_range("my_metric", start, end, step_seconds=300)

    assert len(captured_url) == 1
    parsed = urlparse(captured_url[0])
    assert parsed.path == "/api/v1/query_range"
    params = parse_qs(parsed.query)
    assert params["query"] == ["my_metric"]
    assert params["step"] == ["300s"]
    assert params["start"] == [start.isoformat()]
    assert params["end"] == [end.isoformat()]
