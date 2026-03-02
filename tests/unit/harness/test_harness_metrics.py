"""Unit tests for harness metric contract compliance.

Verifies that all Gauge names and label sets in harness/metrics.py exactly match
the canonical definitions in config/policies/prometheus-metrics-contract-v1.yaml.
"""
import pathlib

import metrics  # importable via conftest sys.path injection
import yaml

_CONTRACT_PATH = (
    pathlib.Path(__file__).parents[3] / "config/policies/prometheus-metrics-contract-v1.yaml"
)


def _load_canonical_names() -> set[str]:
    with open(_CONTRACT_PATH) as f:
        contract = yaml.safe_load(f)
    return {defn["canonical"] for defn in contract["metrics"].values()}


def _load_contract_identity() -> dict:
    with open(_CONTRACT_PATH) as f:
        return yaml.safe_load(f)["identity"]


def _gauge_name(gauge) -> str:
    """Return metric name via the public describe() API."""
    return gauge.describe()[0].name


_TOPIC_GAUGES = [
    metrics.messages_in,
    metrics.bytes_in,
    metrics.bytes_out,
    metrics.failed_produce,
    metrics.failed_fetch,
    metrics.total_produce,
    metrics.total_fetch,
]
_LAG_GAUGES = [metrics.group_lag, metrics.group_offset]


def test_all_harness_metric_names_are_canonical():
    canonical = _load_canonical_names()
    for gauge in _TOPIC_GAUGES + _LAG_GAUGES:
        name = _gauge_name(gauge)
        assert name in canonical, (
            f"Harness metric '{name}' is NOT in prometheus-metrics-contract-v1 canonical names. "
            f"Valid names: {sorted(canonical)}"
        )


def test_topic_metric_labels_match_contract():
    identity = _load_contract_identity()
    expected = sorted(identity["topic_identity_labels"])
    assert sorted(metrics.TOPIC_LABELS) == expected, (
        f"metrics.TOPIC_LABELS {sorted(metrics.TOPIC_LABELS)} != contract {expected}"
    )
    label_kwargs = {label: "test" for label in expected}
    for gauge in _TOPIC_GAUGES:
        # labels() raises ValueError if label names don't exactly match
        gauge.labels(**label_kwargs)


def test_lag_metric_labels_match_contract():
    identity = _load_contract_identity()
    expected = sorted(identity["lag_identity_labels"])
    assert sorted(metrics.LAG_LABELS) == expected, (
        f"metrics.LAG_LABELS {sorted(metrics.LAG_LABELS)} != contract {expected}"
    )
    label_kwargs = {label: "test" for label in expected}
    for gauge in _LAG_GAUGES:
        # labels() raises ValueError if label names don't exactly match
        gauge.labels(**label_kwargs)


def test_pattern_consumer_lag_is_callable():
    from patterns import consumer_lag

    consumer_lag.run(duration=1, intensity=0.5)  # must complete in ~1s without error


def test_pattern_throughput_proxy_is_callable():
    from patterns import throughput_proxy

    throughput_proxy.run(duration=1, intensity=0.5)


def test_pattern_volume_drop_is_callable():
    from patterns import volume_drop

    volume_drop.run(duration=1, intensity=0.5)


def test_pattern_normal_is_callable():
    from patterns import normal

    normal.run(duration=1, intensity=0.5)
