from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

from aiops_triage_pipeline.contracts.enums import CriticalityTier
from aiops_triage_pipeline.registry.loader import (
    CanonicalOwnershipMap,
    CanonicalTopicEntry,
    CanonicalTopologyRegistry,
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
