import pytest

from aiops_triage_pipeline.integrations.prometheus import (
    DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH,
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
