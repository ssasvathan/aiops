"""OTLP metric exporter bootstrap for application processes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as GrpcOTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as HttpOTLPMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.logging.setup import get_logger

_logger = get_logger("health.otlp")
_bootstrap_lock = Lock()
_meter_provider: MeterProvider | None = None


@dataclass(frozen=True)
class OtlpBootstrapResult:
    configured: bool
    reason: str


def configure_otlp_metrics(settings: Settings) -> OtlpBootstrapResult:
    """Configure a process-wide OTLP metrics pipeline when endpoint is set.

    The bootstrap is idempotent and safe to call repeatedly from process
    entrypoints. When OTLP endpoint is not configured, this is a no-op.
    """
    endpoint = settings.OTLP_METRICS_ENDPOINT
    if endpoint is None or endpoint.strip() == "":
        return OtlpBootstrapResult(configured=False, reason="otlp_endpoint_not_configured")

    global _meter_provider
    with _bootstrap_lock:
        if _meter_provider is not None:
            return OtlpBootstrapResult(configured=True, reason="already_configured")

        headers = _parse_otlp_headers(settings.OTLP_METRICS_HEADERS)
        exporter = _build_otlp_exporter(
            endpoint=endpoint,
            protocol=settings.OTLP_METRICS_PROTOCOL,
            headers=headers,
            timeout_millis=settings.OTLP_METRICS_TIMEOUT_MILLIS,
        )
        reader = PeriodicExportingMetricReader(
            exporter=exporter,
            export_interval_millis=settings.OTLP_METRICS_EXPORT_INTERVAL_MILLIS,
        )
        _resource_attrs: dict[str, str] = {
            "service.name": settings.OTLP_SERVICE_NAME,
            "service.version": settings.OTLP_SERVICE_VERSION,
            "deployment.environment": settings.OTLP_DEPLOYMENT_ENVIRONMENT,
        }
        _pod_name = os.getenv("POD_NAME")
        _pod_namespace = os.getenv("POD_NAMESPACE")
        if _pod_name:
            _resource_attrs["k8s.pod.name"] = _pod_name
        if _pod_namespace:
            _resource_attrs["k8s.namespace.name"] = _pod_namespace
        provider = MeterProvider(
            resource=Resource.create(_resource_attrs),
            metric_readers=[reader],
        )
        metrics.set_meter_provider(provider)
        _meter_provider = provider

    _logger.info(
        "otlp_metrics_configured",
        event_type="health.otlp.configured",
        endpoint=endpoint,
        protocol=settings.OTLP_METRICS_PROTOCOL,
        export_interval_millis=settings.OTLP_METRICS_EXPORT_INTERVAL_MILLIS,
        service_name=settings.OTLP_SERVICE_NAME,
        service_version=settings.OTLP_SERVICE_VERSION,
        deployment_environment=settings.OTLP_DEPLOYMENT_ENVIRONMENT,
        headers_configured=bool(settings.OTLP_METRICS_HEADERS),
    )
    return OtlpBootstrapResult(configured=True, reason="configured")


def force_flush_otlp_metrics(timeout_millis: int = 10000) -> bool:
    """Flush pending metric exports if OTLP provider has been configured."""
    provider = _meter_provider
    if provider is None:
        return False
    return provider.force_flush(timeout_millis=timeout_millis)


def shutdown_otlp_metrics(timeout_millis: int = 10000) -> bool:
    """Shut down the OTLP meter provider and stop background export loops."""
    global _meter_provider
    provider = _meter_provider
    if provider is None:
        return False
    try:
        return provider.shutdown(timeout_millis=timeout_millis)
    finally:
        _meter_provider = None


def _build_otlp_exporter(
    *,
    endpoint: str,
    protocol: str,
    headers: dict[str, str] | None,
    timeout_millis: int,
) -> object:
    if protocol == "grpc":
        return GrpcOTLPMetricExporter(
            endpoint=endpoint,
            headers=headers,
            timeout=timeout_millis / 1000,
        )
    return HttpOTLPMetricExporter(
        endpoint=endpoint,
        headers=headers,
        timeout=timeout_millis / 1000,
    )


def _parse_otlp_headers(raw_headers: str | None) -> dict[str, str] | None:
    if raw_headers is None:
        return None

    header_pairs = [segment.strip() for segment in raw_headers.split(",") if segment.strip()]
    if not header_pairs:
        return None

    parsed: dict[str, str] = {}
    for header_pair in header_pairs:
        key, separator, value = header_pair.partition("=")
        if separator != "=":
            raise ValueError(
                "OTLP_METRICS_HEADERS must use comma-separated key=value pairs"
            )
        key = key.strip()
        value = value.strip()
        if key == "" or value == "":
            raise ValueError(
                "OTLP_METRICS_HEADERS entries must contain non-empty key and value"
            )
        parsed[key] = value
    return parsed
