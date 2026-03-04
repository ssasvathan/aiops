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
    assert scope in output.unresolved_by_scope
    assert output.unresolved_by_scope[scope].status == "unresolved"
    assert output.unresolved_by_scope[scope].reason_code == "topic_not_found"
