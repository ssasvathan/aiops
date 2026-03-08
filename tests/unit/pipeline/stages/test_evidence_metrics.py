from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from urllib.error import URLError

import pytest

from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition
from aiops_triage_pipeline.pipeline.stages.evidence import (
    collect_evidence_stage_output,
    collect_prometheus_samples_with_diagnostics,
)


def test_collect_evidence_stage_output_records_unknown_rate_per_metric_key() -> None:
    samples_by_metric = {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 12.0,
            }
        ],
        "consumer_group_lag": [],
    }

    with patch(
        "aiops_triage_pipeline.pipeline.stages.evidence.record_evidence_unknown_rate"
    ) as record_unknown_rate:
        output = collect_evidence_stage_output(samples_by_metric)

    assert output.rows
    assert record_unknown_rate.call_count == 2
    first_call = record_unknown_rate.call_args_list[0].kwargs
    second_call = record_unknown_rate.call_args_list[1].kwargs
    assert first_call["metric_key"] == "topic_messages_in_per_sec"
    assert second_call["metric_key"] == "consumer_group_lag"
    assert first_call["total_count"] == 1
    assert second_call["unknown_count"] == 1


@pytest.mark.asyncio
async def test_collect_prometheus_samples_with_diagnostics_records_scrape_outcomes() -> None:
    class _Client:
        def query_instant(self, metric_name: str, at_time: datetime) -> list[dict]:  # noqa: ARG002
            if metric_name == "ok.metric":
                return [
                    {
                        "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                        "value": 1.0,
                    }
                ]
            raise URLError("source unavailable")

    metric_queries = {
        "ok": MetricQueryDefinition(metric_key="ok", metric_name="ok.metric", role="signal"),
        "bad": MetricQueryDefinition(metric_key="bad", metric_name="bad.metric", role="signal"),
    }
    with patch(
        "aiops_triage_pipeline.pipeline.stages.evidence.record_prometheus_scrape_result"
    ) as record_scrape:
        diagnostics = await collect_prometheus_samples_with_diagnostics(
            client=_Client(),
            metric_queries=metric_queries,
            evaluation_time=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
        )

    assert diagnostics.failed_metric_keys == ("bad",)
    assert record_scrape.call_args_list[0].kwargs == {"metric_key": "ok", "success": True}
    assert record_scrape.call_args_list[1].kwargs == {"metric_key": "bad", "success": False}
