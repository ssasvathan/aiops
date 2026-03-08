"""OTLP metric definitions for component health and pipeline telemetry."""

from threading import Lock

from opentelemetry import metrics

from aiops_triage_pipeline.models.health import HealthStatus

_meter = metrics.get_meter("aiops_triage_pipeline.health")
_state_lock = Lock()

_STATUS_VALUES: dict[HealthStatus, int] = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNAVAILABLE: 2,
}
_CONNECTION_VALUES = {
    True: 1,
    False: 0,
}

_component_health_gauge = _meter.create_up_down_counter(
    name="aiops.component.health_status",
    description="Current health status per component: 0=HEALTHY, 1=DEGRADED, 2=UNAVAILABLE",
    unit="1",
)
_llm_cold_path_inflight = _meter.create_up_down_counter(
    name="aiops.llm.cold_path.inflight",
    description="Number of in-flight cold-path LLM diagnosis invocations",
    unit="1",
)
_llm_invocations_total = _meter.create_counter(
    name="aiops.llm.invocations_total",
    description="Total LLM cold-path invocations by result",
    unit="1",
)
_llm_latency_seconds = _meter.create_histogram(
    name="aiops.llm.latency_seconds",
    description="LLM cold-path invocation latency in seconds",
    unit="s",
)
_llm_timeouts_total = _meter.create_counter(
    name="aiops.llm.timeouts_total",
    description="Total LLM cold-path timeouts",
    unit="1",
)
_llm_errors_total = _meter.create_counter(
    name="aiops.llm.errors_total",
    description="Total LLM cold-path errors by error type",
    unit="1",
)
_llm_fallbacks_total = _meter.create_counter(
    name="aiops.llm.fallbacks_total",
    description="Total LLM fallback reports emitted by reason code",
    unit="1",
)
_redis_connection_status = _meter.create_up_down_counter(
    name="aiops.redis.connection_status",
    description="Redis connection status gauge encoded as 1=healthy, 0=degraded",
    unit="1",
)
_redis_dedupe_cache_hits_total = _meter.create_counter(
    name="aiops.redis.dedupe.cache_hits_total",
    description="Redis AG5 dedupe cache hits",
    unit="1",
)
_redis_dedupe_cache_misses_total = _meter.create_counter(
    name="aiops.redis.dedupe.cache_misses_total",
    description="Redis AG5 dedupe cache misses",
    unit="1",
)
_redis_dedupe_key_count = _meter.create_up_down_counter(
    name="aiops.redis.dedupe.key_count",
    description="Approximate in-process count of active AG5 dedupe keys",
    unit="1",
)
_evidence_interval_drift_seconds = _meter.create_histogram(
    name="aiops.evidence_builder.interval_drift_seconds",
    description="Observed scheduler interval drift in seconds",
    unit="s",
)
_evidence_interval_adherence_total = _meter.create_counter(
    name="aiops.evidence_builder.interval_adherence_total",
    description="Scheduler interval adherence counters by status",
    unit="1",
)
_evidence_unknown_rate = _meter.create_histogram(
    name="aiops.evidence_builder.unknown_rate",
    description="UNKNOWN evidence rate (0..1) by metric key",
    unit="1",
)
_prometheus_scrape_total = _meter.create_counter(
    name="aiops.prometheus.scrape_total",
    description="Prometheus scrape outcomes by metric key and status",
    unit="1",
)
_prometheus_degraded_active = _meter.create_up_down_counter(
    name="aiops.prometheus.telemetry_degraded_active",
    description="Prometheus telemetry degraded state (1=active, 0=cleared)",
    unit="1",
)
_prometheus_degraded_transitions_total = _meter.create_counter(
    name="aiops.prometheus.telemetry_degraded_transitions_total",
    description="Prometheus degraded state transitions",
    unit="1",
)
_pipeline_compute_latency_seconds = _meter.create_histogram(
    name="aiops.pipeline.compute_latency_seconds",
    description="Pipeline compute latency by stage",
    unit="s",
)
_pipeline_cases_per_interval = _meter.create_histogram(
    name="aiops.pipeline.cases_per_interval",
    description="Cases produced per evaluation interval",
    unit="1",
)

_prev_status_values: dict[str, int] = {}
_prev_connection_values: dict[str, int] = {"redis": 1}
_redis_dedupe_key_count_value = 0
_prometheus_degraded_active_value = 0


def llm_inflight_add(delta: int) -> None:
    _llm_cold_path_inflight.add(delta, attributes={"component": "llm"})


def record_status(component: str, status: HealthStatus) -> None:
    with _state_lock:
        new_val = _STATUS_VALUES[status]
        old_val = _prev_status_values.get(component, 0)
        _prev_status_values[component] = new_val
    _component_health_gauge.add(new_val - old_val, attributes={"component": component})


def record_redis_connection_status(*, healthy: bool) -> None:
    with _state_lock:
        new_val = _CONNECTION_VALUES[healthy]
        old_val = _prev_connection_values.get("redis", 1)
        _prev_connection_values["redis"] = new_val
    _redis_connection_status.add(new_val - old_val, attributes={"component": "redis"})


def record_redis_dedupe_lookup(*, hit: bool) -> None:
    if hit:
        _redis_dedupe_cache_hits_total.add(1, attributes={"component": "redis"})
        return
    _redis_dedupe_cache_misses_total.add(1, attributes={"component": "redis"})


def record_redis_dedupe_key_count_delta(*, delta: int) -> None:
    if delta == 0:
        return
    with _state_lock:
        global _redis_dedupe_key_count_value
        new_value = max(_redis_dedupe_key_count_value + delta, 0)
        applied_delta = new_value - _redis_dedupe_key_count_value
        _redis_dedupe_key_count_value = new_value
    if applied_delta != 0:
        _redis_dedupe_key_count.add(applied_delta, attributes={"component": "redis"})


def record_llm_invocation(*, result: str) -> None:
    _llm_invocations_total.add(1, attributes={"result": result, "component": "llm"})


def record_llm_latency(*, seconds: float, result: str) -> None:
    _llm_latency_seconds.record(
        max(seconds, 0.0),
        attributes={"result": result, "component": "llm"},
    )


def record_llm_timeout() -> None:
    _llm_timeouts_total.add(1, attributes={"component": "llm"})


def record_llm_error(*, error_type: str) -> None:
    _llm_errors_total.add(
        1,
        attributes={"component": "llm", "error_type": error_type},
    )


def record_llm_fallback(*, reason_code: str) -> None:
    _llm_fallbacks_total.add(
        1,
        attributes={"component": "llm", "reason_code": reason_code},
    )


def record_evidence_interval_tick(
    *,
    drift_seconds: int,
    missed_intervals: int,
    interval_seconds: int,
) -> None:
    _evidence_interval_drift_seconds.record(
        max(float(drift_seconds), 0.0),
        attributes={"component": "scheduler"},
    )
    status = "on_time"
    if missed_intervals > 0:
        status = "missed"
    elif drift_seconds > 0:
        status = "drifted"
    _evidence_interval_adherence_total.add(
        1,
        attributes={
            "status": status,
            "component": "scheduler",
            "interval_seconds": str(interval_seconds),
        },
    )


def record_evidence_unknown_rate(
    *,
    metric_key: str,
    unknown_count: int,
    total_count: int,
) -> None:
    # No denominator means no meaningful rate; avoid emitting synthetic 0.0.
    if total_count <= 0:
        return
    rate = min(max(unknown_count / total_count, 0.0), 1.0)
    _evidence_unknown_rate.record(
        rate,
        attributes={
            "metric_key": metric_key,
            "component": "evidence_builder",
        },
    )


def record_prometheus_scrape_result(*, metric_key: str, success: bool) -> None:
    _prometheus_scrape_total.add(
        1,
        attributes={
            "metric_key": metric_key,
            "status": "success" if success else "failure",
            "component": "prometheus",
        },
    )


def record_prometheus_degraded_active(*, active: bool) -> None:
    with _state_lock:
        global _prometheus_degraded_active_value
        new_val = 1 if active else 0
        delta = new_val - _prometheus_degraded_active_value
        _prometheus_degraded_active_value = new_val
    if delta != 0:
        _prometheus_degraded_active.add(delta, attributes={"component": "prometheus"})


def record_prometheus_degraded_transition(*, transition: str) -> None:
    _prometheus_degraded_transitions_total.add(
        1,
        attributes={"transition": transition, "component": "prometheus"},
    )


def record_pipeline_compute_latency(*, stage: str, seconds: float) -> None:
    _pipeline_compute_latency_seconds.record(
        max(seconds, 0.0),
        attributes={"stage": stage, "component": "pipeline"},
    )


def record_pipeline_case_throughput(*, case_count: int) -> None:
    _pipeline_cases_per_interval.record(
        max(float(case_count), 0.0),
        attributes={"component": "pipeline"},
    )
