import io
import json
from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.contracts.enums import EvidenceStatus
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.pipeline.stages.evidence import (
    build_evidence_scope_key,
    collect_evidence_rows,
    collect_evidence_stage_output,
    collect_prometheus_samples,
)


def test_build_evidence_scope_key_for_topic_metric() -> None:
    labels = {
        "env": "prod",
        "cluster_name": "cluster-1",
        "topic": "orders",
    }

    assert build_evidence_scope_key(labels, metric_key="topic_messages_in_per_sec") == (
        "prod",
        "cluster-1",
        "orders",
    )


def test_build_evidence_scope_key_for_lag_metric_includes_group() -> None:
    labels = {
        "env": "prod",
        "cluster_name": "cluster-1",
        "group": "consumer-a",
        "topic": "orders",
    }

    assert build_evidence_scope_key(labels, metric_key="consumer_group_lag") == (
        "prod",
        "cluster-1",
        "consumer-a",
        "orders",
    )


def test_collect_evidence_rows_applies_normalization_and_scoping() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "dev", "cluster_name": "east-1", "topic": "payments"},
                "value": 12.5,
            }
        ],
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "dev",
                    "cluster_name": "east-1",
                    "group": "processor",
                    "topic": "payments",
                },
                "value": 3.0,
            }
        ],
    }

    rows = collect_evidence_rows(samples)

    assert [row.scope for row in rows] == [
        ("dev", "east-1", "payments"),
        ("dev", "east-1", "processor", "payments"),
    ]
    assert all(row.labels["cluster_id"] == "east-1" for row in rows)


async def test_collect_prometheus_samples_logs_warning_for_unavailable_metric(
    log_stream: io.StringIO,
) -> None:
    class _FailingClient:
        def query_instant(self, metric_name: str, at_time: datetime) -> list:  # noqa: ARG002
            raise URLError(f"upstream unavailable for {metric_name}")

    metric_queries = {
        "topic_messages_in_per_sec": MetricQueryDefinition(
            metric_key="topic_messages_in_per_sec",
            metric_name="kafka_server_brokertopicmetrics_messagesinpersec",
            role="signal",
        )
    }
    collected = await collect_prometheus_samples(
        client=_FailingClient(),
        metric_queries=metric_queries,
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )

    assert collected["topic_messages_in_per_sec"] == []
    logs = [
        json.loads(line)
        for line in log_stream.getvalue().splitlines()
        if line.strip() and json.loads(line).get("event") == "prometheus_collection_missed_window"
    ]
    assert len(logs) == 1
    assert logs[0]["severity"] == "WARNING"


def test_build_evidence_scope_key_raises_for_missing_env_label() -> None:
    labels = {"cluster_name": "cluster-1", "topic": "orders"}  # no 'env'
    with pytest.raises(ValueError, match="env"):
        build_evidence_scope_key(labels, metric_key="topic_messages_in_per_sec")


def test_build_evidence_scope_key_raises_for_missing_topic_label() -> None:
    labels = {"env": "prod", "cluster_name": "cluster-1"}  # no 'topic'
    with pytest.raises(ValueError, match="topic"):
        build_evidence_scope_key(labels, metric_key="topic_messages_in_per_sec")


def test_collect_evidence_rows_skips_malformed_sample_with_warning(
    log_stream: io.StringIO,
) -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {"labels": {"cluster_name": "east-1", "topic": "orders"}, "value": 5.0},  # missing env
            {"labels": {"env": "dev", "cluster_name": "east-1", "topic": "orders"}, "value": 2.0},
        ]
    }
    rows = collect_evidence_rows(samples)

    assert len(rows) == 1
    assert rows[0].value == 2.0
    logs = [
        json.loads(line)
        for line in log_stream.getvalue().splitlines()
        if line.strip() and json.loads(line).get("event") == "evidence_row_normalization_failed"
    ]
    assert len(logs) == 1
    assert logs[0]["severity"] == "WARNING"


def test_evidence_row_is_immutable() -> None:
    row = EvidenceRow(
        metric_key="topic_messages_in_per_sec",
        value=5.0,
        labels={"env": "dev", "cluster_name": "east-1", "cluster_id": "east-1", "topic": "orders"},
        scope=("dev", "east-1", "orders"),
    )
    with pytest.raises(Exception):
        row.value = 99.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        row.labels["topic"] = "mutated"


def test_collect_evidence_stage_output_includes_anomaly_findings_by_scope() -> None:
    samples = {
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "east-1",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 120.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "east-1",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 180.0,
            }
        ],
        "consumer_group_offset": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "east-1",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 2.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "east-1",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 7.0,
            }
        ],
    }

    output = collect_evidence_stage_output(samples)

    scope = ("prod", "east-1", "payments-worker", "payments")
    assert scope in output.anomaly_result.findings_by_scope
    assert output.anomaly_result.findings_by_scope[scope][0].anomaly_family == "CONSUMER_LAG"
    assert scope in output.gate_findings_by_scope
    assert output.gate_findings_by_scope[scope][0].evidence_required == (
        "consumer_group_lag",
        "consumer_group_offset",
    )
    with pytest.raises(TypeError):
        output.gate_findings_by_scope[scope] = ()


def test_evidence_stage_output_detects_harness_like_patterns() -> None:
    """End-to-end shape verification: all three anomaly families detected from realistic data."""
    samples = {
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 120.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 180.0,
            },
        ],
        "consumer_group_offset": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 2.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 8.0,
            },
        ],
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 1400.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 180.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 0.4,
            },
        ],
        "total_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 200.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "inventory"},
                "value": 220.0,
            },
        ],
        "failed_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 24.0,
            }
        ],
    }

    output = collect_evidence_stage_output(samples)
    families = {finding.anomaly_family for finding in output.anomaly_result.findings}

    assert "CONSUMER_LAG" in families
    assert "THROUGHPUT_CONSTRAINED_PROXY" in families
    assert "VOLUME_DROP" in families
    assert ("prod", "cluster-a", "payments-worker", "payments") in output.gate_findings_by_scope
    assert ("prod", "cluster-a", "orders") in output.gate_findings_by_scope
    assert ("prod", "cluster-a", "inventory") in output.gate_findings_by_scope


def test_collect_evidence_stage_output_preserves_unknown_not_zero_semantics() -> None:
    samples = {
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "east-1",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 180.0,
            }
        ]
    }

    output = collect_evidence_stage_output(samples)

    assert output.anomaly_result.findings == ()
    assert output.gate_findings_by_scope == {}


def test_collect_evidence_stage_output_builds_evidence_status_map_by_scope() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 18.0,
            }
        ],
        "total_produce_requests_per_sec": [],
        "failed_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 4.0,
            }
        ],
    }

    output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "orders")

    assert output.evidence_status_map_by_scope[scope] == {
        "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
        "total_produce_requests_per_sec": EvidenceStatus.UNKNOWN,
        "failed_produce_requests_per_sec": EvidenceStatus.PRESENT,
    }


def test_evidence_stage_output_evidence_status_map_is_immutable() -> None:
    samples = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 18.0,
            }
        ],
        "total_produce_requests_per_sec": [],
    }
    output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "orders")

    with pytest.raises(TypeError):
        output.evidence_status_map_by_scope[scope] = {}
    with pytest.raises(TypeError):
        output.evidence_status_map_by_scope[scope]["total_produce_requests_per_sec"] = (
            EvidenceStatus.PRESENT
        )
