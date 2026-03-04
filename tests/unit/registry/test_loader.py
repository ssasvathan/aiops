from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from time import perf_counter

import pytest
from pydantic import BaseModel

from aiops_triage_pipeline.registry.loader import (
    TopologyRegistryLoader,
    TopologyRegistryValidationError,
    load_topology_registry,
)


def _write_registry(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _to_plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return {name: _to_plain(getattr(value, name)) for name in value.__class__.model_fields}
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_to_plain(item) for item in value]
    return value


def _v0_registry_yaml() -> str:
    return """
version: 1
streams:
  - stream_id: payments-stream
    env: prod
    description: Payments stream
    criticality_tier: TIER_0
    owners:
      platform_team: streaming-platform-ops
    topics:
      source_stream: payments-source
    sources:
      - source_system: Payments
        source_topic: payments-topic
        criticality_tier: TIER_0
topic_index:
  payments-topic:
    role: SOURCE_TOPIC
    stream_id: payments-stream
    source_system: Payments
  payments-source:
    role: KAFKA_SOURCE_STREAM
    stream_id: payments-stream
"""


def _v1_registry_yaml() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: kafka-platform-ops
    owning_team_name: Kafka Platform Ops
    support_channel: "#platform-kafka-ops"
ownership_map:
  consumer_group_owners: []
  topic_owners: []
  stream_default_owner: []
streams:
  - stream_id: payments-stream
    description: Payments stream
    criticality_tier: TIER_0
    owners:
      platform_team: streaming-platform-ops
    instances:
      - env: prod
        cluster_id: Business_Essential
        topics:
          source_stream: payments-source
        sources:
          - source_system: Payments
            source_topic: payments-topic
            criticality_tier: TIER_0
        topic_index:
          payments-topic:
            role: SOURCE_TOPIC
            stream_id: payments-stream
            source_system: Payments
          payments-source:
            role: KAFKA_SOURCE_STREAM
            stream_id: payments-stream
"""


def _v1_registry_yaml_with_duplicate_topic_index() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: kafka-platform-ops
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners: []
  topic_owners: []
  stream_default_owner: []
streams:
  - stream_id: payments-stream
    instances:
      - env: prod
        cluster_id: Business_Essential
        topic_index:
          payments-topic:
            role: SOURCE_TOPIC
            stream_id: payments-stream
          payments-topic:
            role: KAFKA_SOURCE_STREAM
            stream_id: payments-stream
"""


def _v1_registry_yaml_with_duplicate_consumer_group_owner() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: kafka-platform-ops
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners:
    - match:
        env: prod
        cluster_id: Business_Essential
        group: payments-consumer
      routing_key: OWN::Streaming::KafkaPlatform::Ops
    - match:
        env: prod
        cluster_id: Business_Essential
        group: payments-consumer
      routing_key: OWN::Streaming::KafkaPlatform::Ops
  topic_owners: []
  stream_default_owner: []
streams:
  - stream_id: payments-stream
    instances:
      - env: prod
        cluster_id: Business_Essential
        topic_index:
          payments-topic:
            role: SOURCE_TOPIC
            stream_id: payments-stream
"""


def _v1_registry_yaml_with_missing_routing_key() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: kafka-platform-ops
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners:
    - match:
        env: prod
        cluster_id: Business_Essential
        group: payments-consumer
      routing_key: OWN::Streaming::KafkaPlatform::Payments
  topic_owners: []
  stream_default_owner: []
streams:
  - stream_id: payments-stream
    instances:
      - env: prod
        cluster_id: Business_Essential
        topic_index:
          payments-topic:
            role: SOURCE_TOPIC
            stream_id: payments-stream
"""


def test_load_v0_registry_canonicalizes_to_in_memory_model(tmp_path: Path) -> None:
    path = tmp_path / "topology-v0.yaml"
    _write_registry(path, _v0_registry_yaml())

    snapshot = load_topology_registry(
        path,
        default_env="prod",
        default_cluster_id="Business_Essential",
    )

    assert snapshot.metadata.input_version == 1
    assert snapshot.metadata.source_path == str(path)
    assert len(snapshot.registry.streams) == 1
    assert ("prod", "Business_Essential") in snapshot.registry.topic_index_by_scope


def test_load_v1_registry_canonicalizes_to_in_memory_model(tmp_path: Path) -> None:
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _v1_registry_yaml())

    snapshot = load_topology_registry(path)

    assert snapshot.metadata.input_version == 2
    assert len(snapshot.registry.streams) == 1
    assert ("prod", "Business_Essential") in snapshot.registry.topic_index_by_scope


def test_v0_and_v1_equivalent_fixtures_produce_identical_canonical_model(tmp_path: Path) -> None:
    path_v0 = tmp_path / "topology-v0.yaml"
    path_v1 = tmp_path / "topology-v1.yaml"
    _write_registry(path_v0, _v0_registry_yaml())
    _write_registry(path_v1, _v1_registry_yaml())

    v0_snapshot = load_topology_registry(
        path_v0,
        default_env="prod",
        default_cluster_id="Business_Essential",
    )
    v1_snapshot = load_topology_registry(path_v1)

    assert _to_plain(v0_snapshot.registry.streams) == _to_plain(v1_snapshot.registry.streams)
    assert _to_plain(v0_snapshot.registry.topic_index_by_scope) == _to_plain(
        v1_snapshot.registry.topic_index_by_scope
    )


def test_loader_output_is_immutable_for_concurrent_reads(tmp_path: Path) -> None:
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _v1_registry_yaml())
    snapshot = load_topology_registry(path)

    scoped_index = snapshot.registry.topic_index_by_scope[("prod", "Business_Essential")]
    with pytest.raises(TypeError):
        scoped_index["another-topic"] = scoped_index["payments-topic"]  # type: ignore[index]


def test_load_fails_fast_on_duplicate_topic_index_keys(tmp_path: Path) -> None:
    path = tmp_path / "bad-duplicate-topic-index.yaml"
    _write_registry(path, _v1_registry_yaml_with_duplicate_topic_index())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "duplicate_topic_index"


def test_load_fails_fast_on_duplicate_consumer_group_ownership_keys(tmp_path: Path) -> None:
    path = tmp_path / "bad-duplicate-consumer-group-owner.yaml"
    _write_registry(path, _v1_registry_yaml_with_duplicate_consumer_group_owner())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "duplicate_consumer_group_owner"


def test_load_fails_fast_on_missing_routing_key_references(tmp_path: Path) -> None:
    path = tmp_path / "bad-missing-routing-key.yaml"
    _write_registry(path, _v1_registry_yaml_with_missing_routing_key())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "missing_routing_key_reference"


def test_reload_if_changed_swaps_model_atomically_after_success(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _v1_registry_yaml())
    loader = TopologyRegistryLoader(path)
    initial = loader.load()

    updated_content = _v1_registry_yaml().replace("payments-stream", "payments-stream-v2")
    _write_registry(path, updated_content)

    changed = loader.reload_if_changed()
    current = loader.get_snapshot()

    assert changed is True
    assert initial.registry.streams[0].stream_id == "payments-stream"
    assert current.registry.streams[0].stream_id == "payments-stream-v2"


def test_reload_with_invalid_input_preserves_last_known_good_model(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _v1_registry_yaml())
    loader = TopologyRegistryLoader(path)
    initial = loader.load()

    _write_registry(path, _v1_registry_yaml_with_missing_routing_key())
    changed = loader.reload_if_changed()
    current = loader.get_snapshot()

    assert changed is False
    assert _to_plain(current.registry) == _to_plain(initial.registry)


def test_reload_on_change_completes_within_five_seconds(tmp_path: Path) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _v1_registry_yaml())
    loader = TopologyRegistryLoader(path)
    loader.load()

    updated_content = _v1_registry_yaml().replace("Payments stream", "Payments stream updated")
    _write_registry(path, updated_content)

    started_at = perf_counter()
    changed = loader.reload_if_changed()
    elapsed = perf_counter() - started_at

    assert changed is True
    assert elapsed < 5.0
