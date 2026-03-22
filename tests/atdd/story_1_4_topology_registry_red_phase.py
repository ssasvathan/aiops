"""ATDD red-phase acceptance tests for Story 1.4 topology ownership and blast radius."""

from __future__ import annotations

from pathlib import Path

import pytest

from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.registry.loader import (
    TopologyRegistryValidationError,
    load_topology_registry,
)
from aiops_triage_pipeline.registry.resolver import resolve_anomaly_scope


def _write_registry(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _legacy_v1_registry_yaml() -> str:
    return """
version: 1
streams:
  - stream_id: orders-stream
    env: prod
    cluster_id: cluster-a
    topics:
      source_stream: orders-source
    sources:
      - source_system: Payments
        source_topic: orders
topic_index:
  orders:
    role: SOURCE_TOPIC
    stream_id: orders-stream
"""


def _v2_registry_yaml_with_routing_and_confidence() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::Payments::Topic
    owning_team_id: team-payments-topic
    owning_team_name: Payments Topic Team
ownership_map:
  consumer_group_owners: []
  topic_owners:
    - match:
        env: prod
        cluster_id: cluster-a
        topic: orders
      routing_key: OWN::Streaming::Payments::Topic
      source: static
      confidence: 0.73
  stream_default_owner: []
  platform_default: OWN::Streaming::Payments::Topic
streams:
  - stream_id: orders-stream
    criticality_tier: TIER_0
    instances:
      - env: prod
        cluster_id: cluster-a
        sources:
          - source_system: Payments
            source_topic: orders
            criticality_tier: TIER_0
        shared_components:
          nifi_flow_id: nifi-orders-main
        sinks:
          - sink_id: edl_orders_events_v1
            type: hdfs_path
            hdfs_path: /edl/source/payments/orders/events/v1
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: orders-stream
"""


def test_p0_settings_default_topology_registry_path_points_to_canonical_config_file() -> None:
    """P0: Story expects canonical runtime location to be the default when env var is unset."""
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )

    assert settings.TOPOLOGY_REGISTRY_PATH == "config/topology-registry.yaml"


def test_p0_loader_rejects_legacy_v1_registry_format(tmp_path: Path) -> None:
    """P0: Story constrains runtime loading to one supported topology schema."""
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _legacy_v1_registry_yaml())

    with pytest.raises(TopologyRegistryValidationError, match="unsupported_version"):
        load_topology_registry(path)


def test_p1_resolver_exposes_selected_owner_confidence_in_diagnostics(tmp_path: Path) -> None:
    """P1: Story requires confidence-aware ownership output in topology resolution path."""
    path = tmp_path / "topology-v2.yaml"
    _write_registry(path, _v2_registry_yaml_with_routing_and_confidence())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "resolved"
    assert result.ownership_routing is not None
    assert result.ownership_routing.lookup_level == "topic_owner"
    assert result.diagnostics["selected_owner_confidence"] == "0.73"


def test_p1_resolver_downstream_impacts_only_list_downstream_components(tmp_path: Path) -> None:
    """P1: Downstream impact list should not include source components."""
    path = tmp_path / "topology-v2.yaml"
    _write_registry(path, _v2_registry_yaml_with_routing_and_confidence())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "resolved"
    assert [impact.component_type for impact in result.downstream_impacts] == [
        "shared_component",
        "sink",
    ]
