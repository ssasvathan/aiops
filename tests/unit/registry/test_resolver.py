from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

import pytest

from aiops_triage_pipeline.contracts.enums import CriticalityTier
from aiops_triage_pipeline.registry.loader import (
    CanonicalOwnershipMap,
    CanonicalStream,
    CanonicalStreamInstance,
    CanonicalTopicEntry,
    CanonicalTopologyRegistry,
    RoutingDirectoryEntry,
    TopicOwnerEntry,
    TopologyRegistryMetadata,
    TopologyRegistrySnapshot,
    load_topology_registry,
)
from aiops_triage_pipeline.registry.resolver import resolve_anomaly_scope


def _write_registry(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _registry_yaml() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::Payments::Consumer
    owning_team_id: team-payments-cg
    owning_team_name: Payments Consumer Team
    support_channel: #payments-consumer
    escalation_policy_ref: pagerduty-payments-consumer
  - routing_key: OWN::Streaming::Payments::Topic
    owning_team_id: team-payments-topic
    owning_team_name: Payments Topic Team
    support_channel: #payments-topic
  - routing_key: OWN::Streaming::Payments::StreamDefault
    owning_team_id: team-payments-stream
    owning_team_name: Payments Stream Team
  - routing_key: OWN::Streaming::Fraud::StreamDefault
    owning_team_id: team-fraud-stream
    owning_team_name: Fraud Stream Team
    service_now_assignment_group: fraud-ops
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: team-platform
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners:
    - match:
        env: prod
        cluster_id: cluster-a
        group: payments-worker
      routing_key: OWN::Streaming::Payments::Consumer
      source: static
      confidence: 1.0
  topic_owners:
    - match:
        env: prod
        cluster_id: cluster-a
        topic: orders
      routing_key: OWN::Streaming::Payments::Topic
      source: static
      confidence: 1.0
  stream_default_owner:
    - match:
        stream_id: orders-stream-a
        env: prod
        cluster_id: cluster-a
      routing_key: OWN::Streaming::Payments::StreamDefault
      source: static
      confidence: 1.0
    - match:
        stream_id: orders-stream-b
        env: prod
        cluster_id: cluster-b
      routing_key: OWN::Streaming::Fraud::StreamDefault
      source: static
      confidence: 1.0
  platform_default: OWN::Streaming::KafkaPlatform::Ops
streams:
  - stream_id: orders-stream-a
    criticality_tier: TIER_0
    instances:
      - env: prod
        cluster_id: cluster-a
        sources:
          - source_system: Payments
            source_topic: orders
            criticality_tier: TIER_0
        shared_components:
          nifi_flow_id: nifi-edl-writer-main
        sinks:
          - sink_id: edl_orders_events_v1
            type: hdfs_path
            hdfs_path: /edl/source/payments/orders/events/v1
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: orders-stream-a
          orders-shared:
            role: STANDARDIZER_SHARED
            stream_id: orders-stream-a
  - stream_id: orders-stream-b
    criticality_tier: TIER_1
    instances:
      - env: prod
        cluster_id: cluster-b
        sources:
          - source_system: Fraud
            source_topic: orders
            criticality_tier: TIER_1
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: orders-stream-b
  - stream_id: sink-stream
    instances:
      - env: prod
        cluster_id: cluster-a
        topic_index:
          sink-topic:
            role: SINK_TOPIC
            stream_id: sink-stream
  - stream_id: unknown-role-stream
    instances:
      - env: prod
        cluster_id: cluster-a
        topic_index:
          unsupported-role-topic:
            role: UNKNOWN_ROLE
            stream_id: unknown-role-stream
  - stream_id: platform-only-stream
    criticality_tier: TIER_1
    instances:
      - env: prod
        cluster_id: cluster-a
        topic_index:
          platform-only-topic:
            role: SOURCE_TOPIC
            stream_id: platform-only-stream
"""


def test_resolve_anomaly_scope_resolves_topic_scope(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "resolved"
    assert result.reason_code == "resolved"
    assert result.stream_id == "orders-stream-a"
    assert result.topic_role == "SOURCE_TOPIC"
    assert result.criticality_tier == CriticalityTier.TIER_0
    assert result.source_system == "Payments"
    assert result.ownership_routing is not None
    assert result.ownership_routing.lookup_level == "topic_owner"
    assert result.ownership_routing.target.routing_key == "OWN::Streaming::Payments::Topic"
    assert result.ownership_routing.target.owning_team_id == "team-payments-topic"
    assert (
        result.diagnostics["ownership_lookup_path"]
        == "topic_owner->stream_default_owner->platform_default"
    )
    assert result.diagnostics["selected_owner_level"] == "topic_owner"


def test_resolve_anomaly_scope_resolves_group_scope(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "payments-worker", "orders"),
    )

    assert result.status == "resolved"
    assert result.stream_id == "orders-stream-a"
    assert result.topic_role == "SOURCE_TOPIC"
    assert result.criticality_tier == CriticalityTier.TIER_0
    assert result.ownership_routing is not None
    assert result.ownership_routing.lookup_level == "consumer_group_owner"
    assert result.ownership_routing.target.routing_key == "OWN::Streaming::Payments::Consumer"
    assert (
        result.diagnostics["ownership_lookup_path"]
        == "consumer_group_owner->topic_owner->stream_default_owner->platform_default"
    )
    assert result.diagnostics["selected_owner_level"] == "consumer_group_owner"


def test_resolve_anomaly_scope_prevents_cross_cluster_topic_collisions(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    cluster_a = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )
    cluster_b = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-b", "orders"),
    )

    assert cluster_a.status == "resolved"
    assert cluster_b.status == "resolved"
    assert cluster_a.stream_id == "orders-stream-a"
    assert cluster_b.stream_id == "orders-stream-b"
    assert cluster_a.ownership_routing is not None
    assert cluster_a.ownership_routing.lookup_level == "topic_owner"
    assert cluster_b.ownership_routing is not None
    assert cluster_b.ownership_routing.lookup_level == "stream_default_owner"
    assert (
        cluster_b.ownership_routing.target.routing_key
        == "OWN::Streaming::Fraud::StreamDefault"
    )


def test_resolve_anomaly_scope_resolves_stream_default_when_topic_owner_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders-shared"),
    )

    assert result.status == "resolved"
    assert result.ownership_routing is not None
    assert result.ownership_routing.lookup_level == "stream_default_owner"
    assert (
        result.ownership_routing.target.routing_key
        == "OWN::Streaming::Payments::StreamDefault"
    )


def test_resolve_anomaly_scope_falls_through_to_platform_default_when_no_other_owner(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "platform-only-topic"),
    )

    assert result.status == "resolved"
    assert result.ownership_routing is not None
    assert result.ownership_routing.lookup_level == "platform_default"
    assert result.ownership_routing.target.routing_key == "OWN::Streaming::KafkaPlatform::Ops"


def test_resolve_anomaly_scope_returns_explicit_unresolved_when_scope_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-z", "orders"),
    )

    assert result.status == "unresolved"
    assert result.reason_code == "scope_not_found"
    assert result.stream_id is None
    assert result.topic_role is None
    assert result.criticality_tier is None
    assert result.blast_radius is None
    assert result.downstream_impacts == ()
    assert result.ownership_routing is None


def test_resolve_anomaly_scope_returns_explicit_unresolved_when_topic_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "unknown-topic"),
    )

    assert result.status == "unresolved"
    assert result.reason_code == "topic_not_found"
    assert result.blast_radius is None
    assert result.downstream_impacts == ()
    assert result.ownership_routing is None


def test_resolve_anomaly_scope_returns_explicit_unresolved_when_stream_missing() -> None:
    registry = CanonicalTopologyRegistry(
        streams=(),
        streams_by_id={},
        topic_index_by_scope={
            ("prod", "cluster-a"): {
                "orders": CanonicalTopicEntry(
                    topic="orders",
                    role="SOURCE_TOPIC",
                    stream_id="missing-stream",
                    source_system="Payments",
                )
            }
        },
        routing_directory={},
        ownership_map=CanonicalOwnershipMap(),
    )
    snapshot = TopologyRegistrySnapshot(
        registry=registry,
        metadata=TopologyRegistryMetadata(
            source_path="inline",
            source_mtime_ns=0,
            input_version=2,
            loaded_at=datetime.now(tz=UTC),
            load_duration_ms=0.0,
        ),
    )

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "unresolved"
    assert result.reason_code == "stream_not_found"
    assert result.blast_radius is None
    assert result.downstream_impacts == ()
    assert result.ownership_routing is None


def test_resolve_anomaly_scope_returns_explicit_unresolved_for_unsupported_topic_role(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "unsupported-role-topic"),
    )

    assert result.status == "unresolved"
    assert result.reason_code == "UNSUPPORTED_TOPIC_ROLE"
    assert result.blast_radius is None
    assert result.downstream_impacts == ()
    assert result.ownership_routing is None


def test_resolve_anomaly_scope_returns_unresolved_for_invalid_ownership_routing_reference() -> None:
    stream = CanonicalStream(
        stream_id="orders-stream",
        instances=(
            CanonicalStreamInstance(
                env="prod",
                cluster_id="cluster-a",
                topic_index={
                    "orders": CanonicalTopicEntry(
                        topic="orders",
                        role="SOURCE_TOPIC",
                        stream_id="orders-stream",
                        source_system="Payments",
                    )
                },
            ),
        ),
    )
    registry = CanonicalTopologyRegistry(
        streams=(stream,),
        streams_by_id={"orders-stream": stream},
        topic_index_by_scope={
            ("prod", "cluster-a"): {
                "orders": CanonicalTopicEntry(
                    topic="orders",
                    role="SOURCE_TOPIC",
                    stream_id="orders-stream",
                    source_system="Payments",
                )
            }
        },
        routing_directory={
            "OWN::Streaming::KafkaPlatform::Ops": RoutingDirectoryEntry(
                routing_key="OWN::Streaming::KafkaPlatform::Ops",
                owning_team_id="team-platform",
                owning_team_name="Kafka Platform Ops",
            )
        },
        ownership_map=CanonicalOwnershipMap(
            topic_owners=(
                TopicOwnerEntry(
                    env="prod",
                    cluster_id="cluster-a",
                    topic="orders",
                    routing_key="OWN::Streaming::Missing::Owner",
                ),
            ),
            platform_default="OWN::Streaming::KafkaPlatform::Ops",
        ),
    )
    snapshot = TopologyRegistrySnapshot(
        registry=registry,
        metadata=TopologyRegistryMetadata(
            source_path="inline",
            source_mtime_ns=0,
            input_version=2,
            loaded_at=datetime.now(tz=UTC),
            load_duration_ms=0.0,
        ),
    )

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "unresolved"
    assert result.reason_code == "routing_key_not_found"
    assert result.ownership_routing is None
    assert result.diagnostics["selected_owner_level"] == "topic_owner"
    assert result.diagnostics["selected_routing_key"] == "OWN::Streaming::Missing::Owner"


def test_resolve_anomaly_scope_returns_unresolved_when_no_owner_match_exists() -> None:
    stream = CanonicalStream(
        stream_id="orders-stream",
        criticality_tier="TIER_1",
        instances=(
            CanonicalStreamInstance(
                env="prod",
                cluster_id="cluster-a",
                topic_index={
                    "orders": CanonicalTopicEntry(
                        topic="orders",
                        role="SOURCE_TOPIC",
                        stream_id="orders-stream",
                        source_system="Payments",
                    )
                },
            ),
        ),
    )
    registry = CanonicalTopologyRegistry(
        streams=(stream,),
        streams_by_id={"orders-stream": stream},
        topic_index_by_scope={
            ("prod", "cluster-a"): {
                "orders": CanonicalTopicEntry(
                    topic="orders",
                    role="SOURCE_TOPIC",
                    stream_id="orders-stream",
                    source_system="Payments",
                )
            }
        },
        routing_directory={},
        ownership_map=CanonicalOwnershipMap(
            consumer_group_owners=(),
            topic_owners=(),
            stream_default_owner=(),
            platform_default=None,
        ),
    )
    snapshot = TopologyRegistrySnapshot(
        registry=registry,
        metadata=TopologyRegistryMetadata(
            source_path="inline",
            source_mtime_ns=0,
            input_version=2,
            loaded_at=datetime.now(tz=UTC),
            load_duration_ms=0.0,
        ),
    )

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "unresolved"
    assert result.reason_code == "owner_not_found"
    assert result.ownership_routing is None
    assert (
        result.diagnostics["ownership_lookup_path"]
        == "topic_owner->stream_default_owner->platform_default"
    )


@pytest.mark.parametrize(
    ("scope", "expected_blast_radius"),
    [
        (("prod", "cluster-a", "orders"), "LOCAL_SOURCE_INGESTION"),
        (("prod", "cluster-a", "orders-shared"), "SHARED_KAFKA_INGESTION"),
        (("prod", "cluster-a", "sink-topic"), "SHARED_KAFKA_INGESTION"),
    ],
)
def test_resolve_anomaly_scope_computes_blast_radius_from_topic_role(
    tmp_path: Path,
    scope: tuple[str, ...],
    expected_blast_radius: str,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(snapshot=snapshot, anomaly_scope=scope)

    assert result.status == "resolved"
    assert result.blast_radius == expected_blast_radius


def test_resolve_anomaly_scope_derives_downstream_impacts_with_deterministic_ordering(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "resolved"
    assert [
        (
            impact.component_type,
            impact.component_id,
            impact.exposure_type,
            impact.risk_status,
        )
        for impact in result.downstream_impacts
    ] == [
        ("shared_component", "nifi_flow_id:nifi-edl-writer-main", "VISIBILITY_ONLY", "AT_RISK"),
        ("sink", "edl_orders_events_v1", "DOWNSTREAM_DATA_FRESHNESS_RISK", "AT_RISK"),
        ("source", "Payments", "DIRECT_COMPONENT_RISK", "AT_RISK"),
    ]


def test_resolve_anomaly_scope_deduplicates_repeated_downstream_components(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(
        path,
        """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: team-platform
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners: []
  topic_owners: []
  stream_default_owner: []
  platform_default: OWN::Streaming::KafkaPlatform::Ops
streams:
  - stream_id: orders-stream
    instances:
      - env: prod
        cluster_id: cluster-a
        sources:
          - source_system: Payments
            source_topic: orders
          - source_system: Payments
            source_topic: orders-replay
        sinks:
          - sink_id: edl_orders_events_v1
          - sink_id: edl_orders_events_v1
        shared_components:
          nifi_flow_id: nifi-edl-writer-main
          nifi_flow_id_alias: nifi-edl-writer-main
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: orders-stream
""",
    )
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "orders"),
    )

    assert result.status == "resolved"
    assert [
        (
            impact.component_type,
            impact.component_id,
            impact.exposure_type,
        )
        for impact in result.downstream_impacts
    ] == [
        ("shared_component", "nifi_flow_id:nifi-edl-writer-main", "VISIBILITY_ONLY"),
        ("shared_component", "nifi_flow_id_alias:nifi-edl-writer-main", "VISIBILITY_ONLY"),
        ("sink", "edl_orders_events_v1", "DOWNSTREAM_DATA_FRESHNESS_RISK"),
        ("source", "Payments", "DIRECT_COMPONENT_RISK"),
    ]


def test_resolve_anomaly_scope_allows_empty_downstream_impacts_when_none_configured(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)

    result = resolve_anomaly_scope(
        snapshot=snapshot,
        anomaly_scope=("prod", "cluster-a", "sink-topic"),
    )

    assert result.status == "resolved"
    assert result.downstream_impacts == ()


def test_resolve_anomaly_scope_p99_latency_is_within_50ms_in_memory(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)
    scopes = (
        ("prod", "cluster-a", "orders"),
        ("prod", "cluster-a", "payments-worker", "orders"),
        ("prod", "cluster-b", "orders"),
    )

    durations_ms: list[float] = []
    for index in range(3_000):
        scope = scopes[index % len(scopes)]
        started_ns = perf_counter_ns()
        result = resolve_anomaly_scope(snapshot=snapshot, anomaly_scope=scope)
        elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000
        durations_ms.append(elapsed_ms)
        assert result.status == "resolved"

    ordered = sorted(durations_ms)
    percentile_99 = ordered[max(int(len(ordered) * 0.99) - 1, 0)]
    assert percentile_99 <= 50.0
