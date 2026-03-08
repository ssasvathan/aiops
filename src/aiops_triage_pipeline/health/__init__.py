"""HealthRegistry + telemetry — asyncio-safe component health tracking."""

from aiops_triage_pipeline.health.otlp import configure_otlp_metrics
from aiops_triage_pipeline.health.registry import HealthRegistry, get_health_registry
from aiops_triage_pipeline.health.server import start_health_server

__all__ = [
    "HealthRegistry",
    "get_health_registry",
    "start_health_server",
    "configure_otlp_metrics",
]
