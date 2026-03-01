"""OTLP metric definitions for component health monitoring.

Story 1.6 scope: define metrics and recording function.
Story 7.2 scope: configure OTLP exporter + Dynatrace pipeline resource attributes.
"""

from opentelemetry import metrics

from aiops_triage_pipeline.models.health import HealthStatus

# Meter — name matches package for traceability in Dynatrace dashboards
_meter = metrics.get_meter("aiops_triage_pipeline.health")

# Numeric encoding: HEALTHY=0, DEGRADED=1, UNAVAILABLE=2
_STATUS_VALUES: dict[HealthStatus, int] = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNAVAILABLE: 2,
}

# UpDownCounter tracks current status per component (not cumulative)
_component_health_gauge = _meter.create_up_down_counter(
    name="aiops.component.health_status",
    description="Current health status per component: 0=HEALTHY, 1=DEGRADED, 2=UNAVAILABLE",
    unit="1",
)


def record_status(component: str, status: HealthStatus) -> None:
    """Record component health status as an OTLP metric.

    Called by HealthRegistry.update() after storing the new status.
    Full OTLP exporter pipeline (resource, OTLP endpoint, Dynatrace headers)
    is configured in Story 7.2.

    Args:
        component: Component identifier matching HealthRegistry component name
        status: The new health status to record
    """
    _component_health_gauge.add(
        _STATUS_VALUES[status],
        attributes={"component": component, "status": status.value},
    )
