from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from time import perf_counter

import pytest
from pydantic import BaseModel

from aiops_triage_pipeline.contracts.topology_registry import TopologyRegistryLoaderRulesV1
from aiops_triage_pipeline.registry.loader import (
    TopologyRegistryCompatibilityError,
    TopologyRegistryLoader,
    TopologyRegistryValidationError,
    build_v0_compat_view,
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


def _v0_registry_yaml_with_ordered_sources_and_sinks() -> str:
    return """
version: 1
streams:
  - stream_id: payments-stream
    env: prod
    cluster_id: Business_Essential
    sources:
      - source_system: Zeta
        source_topic: z-topic
      - source_system: Alpha
        source_topic: a-topic
    sinks:
      - sink_system: ZetaSink
        sink_topic: z-sink
      - sink_system: AlphaSink
        sink_topic: a-sink
topic_index:
  z-topic:
    role: SOURCE_TOPIC
    stream_id: payments-stream
  a-topic:
    role: SOURCE_TOPIC
    stream_id: payments-stream
"""


def _v1_registry_yaml() -> str:
    return """
version: 2
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


def _v1_registry_yaml_with_unknown_topic_role() -> str:
    return """
version: 2
streams:
  - stream_id: payments-stream
    instances:
      - env: prod
        cluster_id: Business_Essential
        topic_index:
          payments-topic:
            role: UNKNOWN_ROLE
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


def _v1_registry_yaml_with_duplicate_topic_owner() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: kafka-platform-ops
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners: []
  topic_owners:
    - match:
        env: prod
        cluster_id: Business_Essential
        topic: payments-topic
      routing_key: OWN::Streaming::KafkaPlatform::Ops
    - match:
        env: prod
        cluster_id: Business_Essential
        topic: payments-topic
      routing_key: OWN::Streaming::KafkaPlatform::Ops
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


def _v1_registry_yaml_with_duplicate_stream_default_owner() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::KafkaPlatform::Ops
    owning_team_id: kafka-platform-ops
    owning_team_name: Kafka Platform Ops
ownership_map:
  consumer_group_owners: []
  topic_owners: []
  stream_default_owner:
    - match:
        stream_id: payments-stream
        env: prod
        cluster_id: Business_Essential
      routing_key: OWN::Streaming::KafkaPlatform::Ops
    - match:
        stream_id: payments-stream
        env: prod
        cluster_id: Business_Essential
      routing_key: OWN::Streaming::KafkaPlatform::Ops
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


def _v1_registry_yaml_with_invalid_confidence() -> str:
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
      confidence: not-a-number
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


def _v1_registry_yaml_with_non_string_source_system() -> str:
    return """
version: 2
streams:
  - stream_id: payments-stream
    instances:
      - env: prod
        cluster_id: Business_Essential
        topic_index:
          payments-topic:
            role: SOURCE_TOPIC
            stream_id: payments-stream
            source_system: 42
"""


def _v1_registry_yaml_with_non_string_topics_mapping_value() -> str:
    return """
version: 2
streams:
  - stream_id: payments-stream
    instances:
      - env: prod
        cluster_id: Business_Essential
        topics:
          source_stream: 123
        topic_index:
          payments-topic:
            role: SOURCE_TOPIC
            stream_id: payments-stream
"""


def _v1_multi_scope_collision_registry_yaml() -> str:
    return """
version: 2
streams:
  - stream_id: payments-stream-cluster-a
    instances:
      - env: prod
        cluster_id: cluster-a
        topics:
          source_stream: payments-source-a
        sources:
          - source_system: Payments
            source_topic: shared-orders
        topic_index:
          shared-orders:
            role: SOURCE_TOPIC
            stream_id: payments-stream-cluster-a
          payments-source-a:
            role: KAFKA_SOURCE_STREAM
            stream_id: payments-stream-cluster-a
  - stream_id: payments-stream-cluster-b
    instances:
      - env: prod
        cluster_id: cluster-b
        topics:
          source_stream: payments-source-b
        sources:
          - source_system: Fraud
            source_topic: shared-orders
        topic_index:
          shared-orders:
            role: SOURCE_TOPIC
            stream_id: payments-stream-cluster-b
          payments-source-b:
            role: KAFKA_SOURCE_STREAM
            stream_id: payments-stream-cluster-b
"""


def _expected_v0_compat_output() -> dict[str, object]:
    return {
        "version": 1,
        "streams": [
            {
                "stream_id": "payments-stream",
                "env": "prod",
                "description": "Payments stream",
                "criticality_tier": "TIER_0",
                "owners": {"platform_team": "streaming-platform-ops"},
                "topics": {"source_stream": "payments-source"},
                "sources": [
                    {
                        "source_system": "Payments",
                        "source_topic": "payments-topic",
                        "criticality_tier": "TIER_0",
                    }
                ],
            }
        ],
        "topic_index": {
            "payments-source": {"role": "KAFKA_SOURCE_STREAM", "stream_id": "payments-stream"},
            "payments-topic": {
                "role": "SOURCE_TOPIC",
                "stream_id": "payments-stream",
                "source_system": "Payments",
            },
        },
    }


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

    assert _to_plain(v0_snapshot.registry) == _to_plain(v1_snapshot.registry)


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


def test_load_fails_fast_on_duplicate_topic_ownership_keys(tmp_path: Path) -> None:
    path = tmp_path / "bad-duplicate-topic-owner.yaml"
    _write_registry(path, _v1_registry_yaml_with_duplicate_topic_owner())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "duplicate_topic_owner"


def test_load_fails_fast_on_duplicate_stream_default_ownership_keys(tmp_path: Path) -> None:
    path = tmp_path / "bad-duplicate-stream-default-owner.yaml"
    _write_registry(path, _v1_registry_yaml_with_duplicate_stream_default_owner())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "duplicate_stream_default_owner"


def test_load_fails_fast_on_missing_routing_key_references(tmp_path: Path) -> None:
    path = tmp_path / "bad-missing-routing-key.yaml"
    _write_registry(path, _v1_registry_yaml_with_missing_routing_key())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "missing_routing_key_reference"


def test_load_allows_missing_routing_key_reference_when_rule_disabled(tmp_path: Path) -> None:
    path = tmp_path / "missing-routing-key-but-allowed.yaml"
    _write_registry(path, _v1_registry_yaml_with_missing_routing_key())

    snapshot = load_topology_registry(
        path,
        rules=TopologyRegistryLoaderRulesV1(routing_key_required=False),
    )

    assert snapshot.metadata.input_version == 2


def test_load_fails_on_unknown_topic_role_when_rule_enabled(tmp_path: Path) -> None:
    path = tmp_path / "unknown-topic-role.yaml"
    _write_registry(path, _v1_registry_yaml_with_unknown_topic_role())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(
            path,
            rules=TopologyRegistryLoaderRulesV1(fail_on_unknown_topic_role=True),
        )

    assert exc_info.value.category == "unknown_topic_role"


def test_load_fails_on_invalid_confidence_value(tmp_path: Path) -> None:
    path = tmp_path / "invalid-confidence.yaml"
    _write_registry(path, _v1_registry_yaml_with_invalid_confidence())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "invalid_consumer_group_owner_entry"


def test_load_fails_on_non_string_optional_source_system(tmp_path: Path) -> None:
    path = tmp_path / "invalid-source-system.yaml"
    _write_registry(path, _v1_registry_yaml_with_non_string_source_system())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "invalid_topic_index_entry"
    assert exc_info.value.offending_key == "prod:Business_Essential:payments-topic.source_system"


def test_load_fails_on_non_string_topics_mapping_value(tmp_path: Path) -> None:
    path = tmp_path / "invalid-topics-mapping-value.yaml"
    _write_registry(path, _v1_registry_yaml_with_non_string_topics_mapping_value())

    with pytest.raises(TopologyRegistryValidationError) as exc_info:
        load_topology_registry(path)

    assert exc_info.value.category == "invalid_instance_entry"
    assert (
        exc_info.value.offending_key
        == "streams[payments-stream].instances[prod:Business_Essential].topics.source_stream"
    )


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


def test_v0_compat_projection_matches_v0_golden_output_field_by_field(tmp_path: Path) -> None:
    path = tmp_path / "topology-v0.yaml"
    _write_registry(path, _v0_registry_yaml())
    snapshot = load_topology_registry(
        path,
        default_env="prod",
        default_cluster_id="Business_Essential",
    )

    compat_view = build_v0_compat_view(
        snapshot=snapshot,
        env="prod",
        cluster_id="Business_Essential",
    )

    assert compat_view.to_legacy_dict() == _expected_v0_compat_output()


def test_v0_compat_projection_from_v1_matches_same_v0_golden_output(tmp_path: Path) -> None:
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _v1_registry_yaml())
    snapshot = load_topology_registry(path)

    compat_view = build_v0_compat_view(
        snapshot=snapshot,
        env="prod",
        cluster_id="Business_Essential",
    )

    assert compat_view.to_legacy_dict() == _expected_v0_compat_output()


def test_v0_compat_projection_is_scope_isolated_for_topic_name_collisions(tmp_path: Path) -> None:
    path = tmp_path / "topology-v1-multi-scope.yaml"
    _write_registry(path, _v1_multi_scope_collision_registry_yaml())
    snapshot = load_topology_registry(path)

    cluster_a = build_v0_compat_view(snapshot=snapshot, env="prod", cluster_id="cluster-a")
    cluster_b = build_v0_compat_view(snapshot=snapshot, env="prod", cluster_id="cluster-b")

    cluster_a_payload = cluster_a.to_legacy_dict()
    cluster_b_payload = cluster_b.to_legacy_dict()
    cluster_a_topic_entry = cluster_a_payload["topic_index"]["shared-orders"]  # type: ignore[index]
    cluster_b_topic_entry = cluster_b_payload["topic_index"]["shared-orders"]  # type: ignore[index]
    assert cluster_a_topic_entry["stream_id"] == "payments-stream-cluster-a"
    assert cluster_b_topic_entry["stream_id"] == "payments-stream-cluster-b"
    assert cluster_a_payload["streams"][0]["stream_id"] == "payments-stream-cluster-a"  # type: ignore[index]
    assert cluster_b_payload["streams"][0]["stream_id"] == "payments-stream-cluster-b"  # type: ignore[index]
    assert cluster_a_payload != cluster_b_payload


def test_v0_compat_projection_fails_loudly_for_unknown_scope(tmp_path: Path) -> None:
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _v1_registry_yaml())
    snapshot = load_topology_registry(path)

    with pytest.raises(TopologyRegistryCompatibilityError) as exc_info:
        build_v0_compat_view(snapshot=snapshot, env="prod", cluster_id="missing-cluster")

    assert exc_info.value.category == "scope_not_found"


def test_v0_compat_projection_fails_loudly_for_invalid_scope_inputs(tmp_path: Path) -> None:
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _v1_registry_yaml())
    snapshot = load_topology_registry(path)

    with pytest.raises(TopologyRegistryCompatibilityError) as exc_info:
        build_v0_compat_view(snapshot=snapshot, env=" ", cluster_id="cluster-a")

    assert exc_info.value.category == "invalid_scope"


@pytest.mark.parametrize(
    ("env", "cluster_id"),
    [
        pytest.param(None, "cluster-a", id="env-none"),
        pytest.param(123, "cluster-a", id="env-int"),
        pytest.param("prod", None, id="cluster-none"),
        pytest.param("prod", 123, id="cluster-int"),
    ],
)
def test_v0_compat_projection_fails_loudly_for_non_string_scope_inputs(
    tmp_path: Path,
    env: object,
    cluster_id: object,
) -> None:
    path = tmp_path / "topology-v1.yaml"
    _write_registry(path, _v1_registry_yaml())
    snapshot = load_topology_registry(path)

    with pytest.raises(TopologyRegistryCompatibilityError) as exc_info:
        build_v0_compat_view(
            snapshot=snapshot,
            env=env,  # type: ignore[arg-type]
            cluster_id=cluster_id,  # type: ignore[arg-type]
        )

    assert exc_info.value.category == "invalid_scope"


def test_v0_compat_projection_preserves_legacy_sources_and_sinks_order(tmp_path: Path) -> None:
    path = tmp_path / "topology-v0-ordered-lists.yaml"
    _write_registry(path, _v0_registry_yaml_with_ordered_sources_and_sinks())
    snapshot = load_topology_registry(
        path,
        default_env="prod",
        default_cluster_id="Business_Essential",
    )

    payload = build_v0_compat_view(
        snapshot=snapshot,
        env="prod",
        cluster_id="Business_Essential",
    ).to_legacy_dict()

    stream = payload["streams"][0]  # type: ignore[index]
    assert [item["source_topic"] for item in stream["sources"]] == ["z-topic", "a-topic"]  # type: ignore[index]
    assert [item["sink_topic"] for item in stream["sinks"]] == ["z-sink", "a-sink"]  # type: ignore[index]


def test_v0_compat_projection_preserves_required_keys_and_types(tmp_path: Path) -> None:
    path = tmp_path / "topology-v0.yaml"
    _write_registry(path, _v0_registry_yaml())
    snapshot = load_topology_registry(
        path,
        default_env="prod",
        default_cluster_id="Business_Essential",
    )

    payload = build_v0_compat_view(
        snapshot=snapshot,
        env="prod",
        cluster_id="Business_Essential",
    ).to_legacy_dict()

    assert type(payload["version"]) is int
    stream = payload["streams"][0]  # type: ignore[index]
    assert type(stream["stream_id"]) is str
    assert type(stream["env"]) is str
    topic_entry = payload["topic_index"]["payments-topic"]  # type: ignore[index]
    assert type(topic_entry["role"]) is str
    assert type(topic_entry["stream_id"]) is str
