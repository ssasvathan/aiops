from __future__ import annotations

from pathlib import Path

from aiops_triage_pipeline.contracts.enums import CriticalityTier
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.topology import collect_topology_stage_output
from aiops_triage_pipeline.registry.loader import load_topology_registry


def _write_registry(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _registry_yaml() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::Payments::Consumer
    owning_team_id: team-payments-cg
    owning_team_name: Payments Consumer Team
  - routing_key: OWN::Streaming::Payments::Topic
    owning_team_id: team-payments-topic
    owning_team_name: Payments Topic Team
  - routing_key: OWN::Streaming::Payments::StreamDefault
    owning_team_id: team-payments-stream
    owning_team_name: Payments Stream Team
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
  topic_owners:
    - match:
        env: prod
        cluster_id: cluster-a
        topic: orders
      routing_key: OWN::Streaming::Payments::Topic
  stream_default_owner:
    - match:
        stream_id: orders-stream
        env: prod
        cluster_id: cluster-a
      routing_key: OWN::Streaming::Payments::StreamDefault
  platform_default: OWN::Streaming::KafkaPlatform::Ops
streams:
  - stream_id: orders-stream
    criticality_tier: TIER_1
    instances:
      - env: prod
        cluster_id: cluster-a
        sources:
          - source_system: Payments
            source_topic: orders
            criticality_tier: TIER_1
        shared_components:
          nifi_flow_id: nifi-edl-writer-main
        sinks:
          - sink_id: edl_orders_events_v1
            type: hdfs_path
            hdfs_path: /edl/source/payments/orders/events/v1
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: orders-stream
"""


def test_collect_topology_stage_output_builds_gate_context_for_topic_and_group_scopes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)
    evidence_output = collect_evidence_stage_output(
        {
            "topic_messages_in_per_sec": [
                {
                    "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                    "value": 180.0,
                },
                {
                    "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                    "value": 0.4,
                },
            ],
            "total_produce_requests_per_sec": [
                {
                    "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                    "value": 220.0,
                }
            ],
            "consumer_group_lag": [
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "group": "payments-worker",
                        "topic": "orders",
                    },
                    "value": 100.0,
                },
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "group": "payments-worker",
                        "topic": "orders",
                    },
                    "value": 140.0,
                },
            ],
            "consumer_group_offset": [
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "group": "payments-worker",
                        "topic": "orders",
                    },
                    "value": 1.0,
                },
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "group": "payments-worker",
                        "topic": "orders",
                    },
                    "value": 2.0,
                },
            ],
        }
    )

    output = collect_topology_stage_output(
        snapshot=snapshot,
        evidence_output=evidence_output,
    )

    topic_scope = ("prod", "cluster-a", "orders")
    group_scope = ("prod", "cluster-a", "payments-worker", "orders")
    assert topic_scope in output.context_by_scope
    assert group_scope in output.context_by_scope
    assert output.context_by_scope[topic_scope].stream_id == "orders-stream"
    assert output.context_by_scope[topic_scope].topic_role == "SOURCE_TOPIC"
    assert output.context_by_scope[topic_scope].criticality_tier == CriticalityTier.TIER_1
    assert output.context_by_scope[topic_scope].source_system == "Payments"
    assert output.impact_by_scope[topic_scope].blast_radius == "LOCAL_SOURCE_INGESTION"
    assert output.impact_by_scope[group_scope].blast_radius == "LOCAL_SOURCE_INGESTION"
    assert output.routing_by_scope[topic_scope].lookup_level == "topic_owner"
    assert output.routing_by_scope[group_scope].lookup_level == "consumer_group_owner"
    assert output.routing_by_scope[topic_scope].routing_key == "OWN::Streaming::Payments::Topic"
    assert output.routing_by_scope[group_scope].routing_key == "OWN::Streaming::Payments::Consumer"
    assert [
        (
            impact.component_type,
            impact.component_id,
            impact.exposure_type,
        )
        for impact in output.impact_by_scope[topic_scope].downstream_impacts
    ] == [
        ("shared_component", "nifi_flow_id:nifi-edl-writer-main", "VISIBILITY_ONLY"),
        ("sink", "edl_orders_events_v1", "DOWNSTREAM_DATA_FRESHNESS_RISK"),
    ]
    assert output.unresolved_by_scope == {}


def test_collect_topology_stage_output_tracks_unresolved_without_fabricating_context(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topology.yaml"
    _write_registry(path, _registry_yaml())
    snapshot = load_topology_registry(path)
    evidence_output = collect_evidence_stage_output(
        {
            "topic_messages_in_per_sec": [
                {
                    "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "missing"},
                    "value": 200.0,
                },
                {
                    "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "missing"},
                    "value": 0.2,
                },
            ],
            "total_produce_requests_per_sec": [
                {
                    "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "missing"},
                    "value": 220.0,
                }
            ],
        }
    )

    output = collect_topology_stage_output(
        snapshot=snapshot,
        evidence_output=evidence_output,
    )

    scope = ("prod", "cluster-a", "missing")
    assert output.context_by_scope == {}
    assert output.impact_by_scope == {}
    assert output.routing_by_scope == {}
    assert scope in output.unresolved_by_scope
    assert output.unresolved_by_scope[scope].status == "unresolved"
    assert output.unresolved_by_scope[scope].reason_code == "topic_not_found"
