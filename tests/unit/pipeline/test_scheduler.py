import io
import json
from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.pipeline.scheduler import (
    SchedulerTick,
    evaluate_scheduler_tick,
    floor_to_interval_boundary,
    next_interval_boundary,
    run_evidence_stage_cycle,
)


def _parse_logs(stream: io.StringIO) -> list[dict]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_floor_to_interval_boundary_aligns_to_5_minute_mark() -> None:
    now = datetime(2026, 3, 2, 12, 7, 42, tzinfo=UTC)
    assert floor_to_interval_boundary(now, interval_seconds=300) == datetime(
        2026, 3, 2, 12, 5, 0, tzinfo=UTC
    )


def test_next_interval_boundary_advances_to_next_5_minute_mark() -> None:
    now = datetime(2026, 3, 2, 12, 5, 0, tzinfo=UTC)
    assert next_interval_boundary(now, interval_seconds=300) == datetime(
        2026, 3, 2, 12, 10, 0, tzinfo=UTC
    )


def test_evaluate_scheduler_tick_tracks_drift_without_warning_under_threshold(
    log_stream: io.StringIO,
) -> None:
    tick = evaluate_scheduler_tick(
        actual_fire_time=datetime(2026, 3, 2, 12, 5, 20, tzinfo=UTC),
        previous_boundary=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        interval_seconds=300,
        drift_threshold_seconds=30,
    )

    assert tick == SchedulerTick(
        expected_boundary=datetime(2026, 3, 2, 12, 5, 0, tzinfo=UTC),
        actual_fire_time=datetime(2026, 3, 2, 12, 5, 20, tzinfo=UTC),
        drift_seconds=20,
        missed_intervals=0,
    )

    warnings = [entry for entry in _parse_logs(log_stream) if entry.get("severity") == "WARNING"]
    assert warnings == []


def test_evaluate_scheduler_tick_warns_when_drift_exceeds_threshold(
    log_stream: io.StringIO,
) -> None:
    _ = evaluate_scheduler_tick(
        actual_fire_time=datetime(2026, 3, 2, 12, 5, 35, tzinfo=UTC),
        previous_boundary=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        interval_seconds=300,
        drift_threshold_seconds=30,
    )

    warning_events = [
        entry
        for entry in _parse_logs(log_stream)
        if entry.get("event") == "scheduler_drift_threshold_exceeded"
    ]
    assert len(warning_events) == 1
    assert warning_events[0]["drift_seconds"] == 35
    assert warning_events[0]["drift_threshold_seconds"] == 30


def test_evaluate_scheduler_tick_warns_for_missed_intervals(
    log_stream: io.StringIO,
) -> None:
    _ = evaluate_scheduler_tick(
        actual_fire_time=datetime(2026, 3, 2, 12, 15, 4, tzinfo=UTC),
        previous_boundary=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
        interval_seconds=300,
        drift_threshold_seconds=30,
    )

    warning_events = [
        entry
        for entry in _parse_logs(log_stream)
        if entry.get("event") == "scheduler_intervals_missed"
    ]
    assert len(warning_events) == 1
    assert warning_events[0]["missed_intervals"] == 2
    assert warning_events[0]["previous_boundary"] == "2026-03-02T12:00:00+00:00"
    assert warning_events[0]["expected_boundary"] == "2026-03-02T12:15:00+00:00"


@pytest.mark.asyncio
async def test_run_evidence_stage_cycle_wires_collection_to_anomaly_output() -> None:
    class _Client:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            if metric_name == "kafka_server_brokertopicmetrics_messagesinpersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 1400.0,
                    }
                ]
            if metric_name == "kafka_server_brokertopicmetrics_totalproducerequestspersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 200.0,
                    }
                ]
            if metric_name == "kafka_server_brokertopicmetrics_failedproducerequestspersec":
                return [
                    {
                        "labels": {
                            "env": "prod",
                            "cluster_name": "cluster-a",
                            "topic": "orders",
                        },
                        "value": 24.0,
                    }
                ]
            return []

    output = await run_evidence_stage_cycle(
        client=_Client(),
        metric_queries={
            "topic_messages_in_per_sec": MetricQueryDefinition(
                metric_key="topic_messages_in_per_sec",
                metric_name="kafka_server_brokertopicmetrics_messagesinpersec",
                role="signal",
            ),
            "total_produce_requests_per_sec": MetricQueryDefinition(
                metric_key="total_produce_requests_per_sec",
                metric_name="kafka_server_brokertopicmetrics_totalproducerequestspersec",
                role="signal",
            ),
            "failed_produce_requests_per_sec": MetricQueryDefinition(
                metric_key="failed_produce_requests_per_sec",
                metric_name="kafka_server_brokertopicmetrics_failedproducerequestspersec",
                role="signal",
            ),
        },
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )

    assert output.rows
    assert ("prod", "cluster-a", "orders") in output.gate_findings_by_scope
