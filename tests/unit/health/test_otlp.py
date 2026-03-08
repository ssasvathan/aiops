from __future__ import annotations

from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.health import otlp


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "bucket",
    }
    base.update(overrides)
    return Settings(**base)


def test_configure_otlp_metrics_noops_when_endpoint_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(otlp, "_meter_provider", None)
    result = otlp.configure_otlp_metrics(_settings())
    assert result.configured is False
    assert result.reason == "otlp_endpoint_not_configured"


def test_configure_otlp_metrics_builds_exporter_with_parsed_headers(monkeypatch) -> None:
    class _FakeReader:
        def __init__(self, *, exporter: object, export_interval_millis: int) -> None:  # noqa: ARG002
            self.exporter = exporter
            self.export_interval_millis = export_interval_millis

    class _FakeProvider:
        def __init__(self, *, resource: object, metric_readers: list[object]) -> None:  # noqa: ARG002
            self.metric_readers = metric_readers

    captured: dict[str, object] = {}

    def _fake_build_otlp_exporter(
        *,
        endpoint: str,
        protocol: str,
        headers: dict[str, str] | None,
        timeout_millis: int,
    ) -> object:
        captured["endpoint"] = endpoint
        captured["protocol"] = protocol
        captured["headers"] = headers
        captured["timeout_millis"] = timeout_millis
        return object()

    monkeypatch.setattr(otlp, "_meter_provider", None)
    monkeypatch.setattr(otlp, "PeriodicExportingMetricReader", _FakeReader)
    monkeypatch.setattr(otlp, "MeterProvider", _FakeProvider)
    monkeypatch.setattr(otlp, "_build_otlp_exporter", _fake_build_otlp_exporter)
    monkeypatch.setattr(otlp.metrics, "set_meter_provider", lambda provider: None)

    settings = _settings(
        OTLP_METRICS_ENDPOINT="http://collector:4318/v1/metrics",
        OTLP_METRICS_PROTOCOL="http/protobuf",
        OTLP_METRICS_HEADERS="Authorization=Api-Token test,tenant=prod",
        OTLP_METRICS_TIMEOUT_MILLIS=4321,
    )
    result = otlp.configure_otlp_metrics(settings)

    assert result.configured is True
    assert captured["endpoint"] == "http://collector:4318/v1/metrics"
    assert captured["protocol"] == "http/protobuf"
    assert captured["timeout_millis"] == 4321
    assert captured["headers"] == {"Authorization": "Api-Token test", "tenant": "prod"}
