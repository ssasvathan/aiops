"""Integration test validating OTLP metrics export through a collector receiver."""

from __future__ import annotations

import re
import time

import pytest

from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.health.metrics import (
    record_llm_fallback,
    record_llm_invocation,
    record_prometheus_degraded_active,
    record_prometheus_degraded_transition,
    record_prometheus_scrape_result,
    record_redis_connection_status,
)
from aiops_triage_pipeline.health.otlp import (
    configure_otlp_metrics,
    force_flush_otlp_metrics,
    shutdown_otlp_metrics,
)
from aiops_triage_pipeline.outbox.metrics import record_outbox_delivery_slo_breach

pytestmark = pytest.mark.integration


def _collector_stderr(container) -> str:
    logs = container.get_logs()
    if isinstance(logs, tuple):
        return logs[1].decode("utf-8", errors="ignore")
    return str(logs)


def _wait_for_log_entries(
    container,
    expected_substrings: tuple[str, ...],
    timeout_seconds: float,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_payload = ""
    while time.monotonic() < deadline:
        last_payload = _collector_stderr(container)
        if all(expected in last_payload for expected in expected_substrings):
            return last_payload
        time.sleep(0.25)
    raise AssertionError(
        "Timed out waiting for expected OTLP-exported metrics in collector logs. "
        f"Missing one of: {expected_substrings}\n\n{last_payload}"
    )


def _extract_metric_values(payload: str, metric_name: str) -> list[float]:
    name_pattern = re.escape(metric_name)
    sections = re.findall(
        rf"Name: {name_pattern}(.*?)(?=\n\s*Name: |\Z)",
        payload,
        flags=re.DOTALL,
    )
    values: list[float] = []
    for section in sections:
        for raw_value in re.findall(
            r"Value:\s*(?:Int|Double)?(?:\()?(?P<value>[-+]?\d+(?:\.\d+)?)(?:\))?",
            section,
        ):
            values.append(float(raw_value))
    return values


def _assert_metric_value_at_least(payload: str, metric_name: str, minimum: float) -> None:
    values = _extract_metric_values(payload, metric_name)
    assert values, f"No exported values found for metric '{metric_name}'"
    assert max(values) >= minimum, (
        f"Expected metric '{metric_name}' to have value >= {minimum}; got values={values}"
    )


def test_otlp_export_collector_receives_metric_names_labels_and_values(
    otlp_collector_container,
) -> None:
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
        OTLP_METRICS_ENDPOINT=otlp_collector_container["otlp_endpoint"],
        OTLP_METRICS_PROTOCOL="http/protobuf",
        OTLP_METRICS_EXPORT_INTERVAL_MILLIS=250,
        OTLP_METRICS_TIMEOUT_MILLIS=5000,
        OTLP_SERVICE_NAME="aiops-triage-pipeline-test",
        OTLP_SERVICE_VERSION="7.2-test",
    )
    configure_otlp_metrics(settings)
    try:
        record_redis_connection_status(healthy=False)
        record_prometheus_scrape_result(metric_key="topic_messages_in_per_sec", success=False)
        record_prometheus_degraded_active(active=True)
        record_prometheus_degraded_transition(transition="active")
        record_llm_invocation(result="fallback")
        record_llm_fallback(reason_code="LLM_TIMEOUT")
        record_outbox_delivery_slo_breach(severity="warning", quantile="p99")

        assert force_flush_otlp_metrics(timeout_millis=10000) is True

        payload = _wait_for_log_entries(
            otlp_collector_container["collector"],
            expected_substrings=(
                "Name: aiops.redis.connection_status",
                "component: Str(redis)",
                "Name: aiops.prometheus.scrape_total",
                "metric_key: Str(topic_messages_in_per_sec)",
                "Name: aiops.llm.fallbacks_total",
                "reason_code: Str(LLM_TIMEOUT)",
                "Name: aiops.outbox.delivery_slo_breaches_total",
                "quantile: Str(p99)",
            ),
            timeout_seconds=30.0,
        )

        assert "Name: aiops.prometheus.telemetry_degraded_transitions_total" in payload
        _assert_metric_value_at_least(payload, "aiops.prometheus.scrape_total", 1.0)
        _assert_metric_value_at_least(payload, "aiops.llm.fallbacks_total", 1.0)
        _assert_metric_value_at_least(payload, "aiops.outbox.delivery_slo_breaches_total", 1.0)
        _assert_metric_value_at_least(
            payload,
            "aiops.prometheus.telemetry_degraded_transitions_total",
            1.0,
        )
    finally:
        shutdown_otlp_metrics(timeout_millis=10000)
