from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aiops_triage_pipeline.pipeline.scheduler import run_topology_stage_cycle
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.registry.loader import load_topology_registry


def _write_registry(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _registry_yaml() -> str:
    return """
version: 2
streams:
  - stream_id: orders-stream
    criticality_tier: TIER_0
    instances:
      - env: prod
        cluster_id: cluster-a
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: orders-stream
"""


def test_run_topology_stage_cycle_prepares_context_for_stage6(tmp_path: Path) -> None:
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
        },
        evaluation_time=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )

    topology_output = run_topology_stage_cycle(
        evidence_output=evidence_output,
        snapshot=snapshot,
    )

    scope = ("prod", "cluster-a", "orders")
    assert scope in topology_output.context_by_scope
    assert topology_output.context_by_scope[scope].stream_id == "orders-stream"
    assert topology_output.unresolved_by_scope == {}
