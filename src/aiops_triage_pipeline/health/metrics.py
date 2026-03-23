"""OTLP metric definitions for component health and pipeline telemetry."""

from collections import deque
from threading import Lock
from typing import Literal, NamedTuple

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
_coordination_cycle_lock_acquired_total = _meter.create_counter(
    name="aiops.coordination.cycle_lock.acquired_total",
    description="Total distributed cycle lock acquisitions",
    unit="1",
)
_coordination_cycle_lock_yielded_total = _meter.create_counter(
    name="aiops.coordination.cycle_lock.yielded_total",
    description="Total distributed cycle lock yielded outcomes",
    unit="1",
)
_coordination_cycle_lock_fail_open_total = _meter.create_counter(
    name="aiops.coordination.cycle_lock.fail_open_total",
    description="Total distributed cycle lock fail-open outcomes",
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
_pipeline_sustained_compute_seconds = _meter.create_histogram(
    name="aiops.pipeline.sustained_compute_seconds",
    description="Sustained-status compute duration",
    unit="s",
)
_pipeline_sustained_key_count = _meter.create_histogram(
    name="aiops.pipeline.sustained_key_count",
    description="Sustained identity keys evaluated per cycle",
    unit="1",
)
_pipeline_cases_per_interval = _meter.create_histogram(
    name="aiops.pipeline.cases_per_interval",
    description="Cases produced per evaluation interval",
    unit="1",
)
_pipeline_peak_history_scope_count = _meter.create_up_down_counter(
    name="aiops.pipeline.peak_history_scope_count",
    description="Current count of in-process peak-history scopes",
    unit="1",
)
_pipeline_peak_history_evictions_total = _meter.create_counter(
    name="aiops.pipeline.peak_history_evictions_total",
    description="Total number of in-process peak-history scope evictions",
    unit="1",
)
_casefile_lifecycle_runs_total = _meter.create_counter(
    name="aiops.casefile_lifecycle.runs_total",
    description="Total number of casefile lifecycle purge runs",
    unit="1",
)
_casefile_lifecycle_objects_total = _meter.create_counter(
    name="aiops.casefile_lifecycle.objects_total",
    description="Casefile lifecycle object counts by outcome",
    unit="1",
)
_sn_correlation_tier_total = _meter.create_up_down_counter(
    name="aiops.servicenow.correlation_tier_total",
    description="Correlation outcomes by tier label",
    unit="1",
)
_sn_correlation_fallback_rate = _meter.create_up_down_counter(
    name="aiops.servicenow.correlation_fallback_rate",
    description="Rolling fallback rate for tier2/tier3 ServiceNow correlations",
    unit="1",
)
_sn_page_linkage_total = _meter.create_up_down_counter(
    name="aiops.servicenow.linkage_page_total",
    description="Terminal PAGE linkage outcomes counted for SLO tracking",
    unit="1",
)
_sn_page_linkage_within_window_total = _meter.create_up_down_counter(
    name="aiops.servicenow.linkage_page_within_window_total",
    description="PAGE linkage outcomes that reached LINKED within retry window",
    unit="1",
)
_sn_page_linkage_within_window_rate = _meter.create_up_down_counter(
    name="aiops.servicenow.linkage_page_within_window_rate",
    description="Rolling rate of PAGE linkage outcomes LINKED within retry window",
    unit="1",
)

_prev_status_values: dict[str, int] = {}
_prev_connection_values: dict[str, int] = {"redis": 1}
_redis_dedupe_key_count_value = 0
_prometheus_degraded_active_value = 0
_pipeline_peak_history_scope_count_value = 0
_sn_correlation_tier_counts: dict[str, int] = {
    "tier1": 0,
    "tier2": 0,
    "tier3": 0,
    "none": 0,
}
_sn_correlation_total_count = 0
_sn_correlation_fallback_rate_value = 0.0
_SN_CORRELATION_RATE_WINDOW_SIZE = 120
_sn_correlation_recent_fallback_flags: deque[int] = deque()
_sn_correlation_recent_fallback_sum = 0
_sn_page_linkage_terminal_count = 0
_sn_page_linkage_within_window_count = 0
_sn_page_linkage_rate_value = 0.0
_SN_PAGE_LINKAGE_RATE_WINDOW_SIZE = 120
_sn_page_linkage_recent_within_window_flags: deque[int] = deque()
_sn_page_linkage_recent_within_window_sum = 0


class ServiceNowCorrelationFallbackSnapshot(NamedTuple):
    fallback_rate: float
    sample_size: int
    fallback_tiers: tuple[str, str]


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


def record_cycle_lock_acquired() -> None:
    _coordination_cycle_lock_acquired_total.add(1, attributes={"component": "coordination"})


def record_cycle_lock_yielded() -> None:
    _coordination_cycle_lock_yielded_total.add(1, attributes={"component": "coordination"})


def record_cycle_lock_fail_open(*, reason: str | None = None) -> None:
    reason_code = "unknown"
    if reason:
        reason_code = reason.split(":", maxsplit=1)[0][:64]
    _coordination_cycle_lock_fail_open_total.add(
        1,
        attributes={"component": "coordination", "reason": reason_code},
    )


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


def record_pipeline_sustained_compute(*, seconds: float, key_count: int, mode: str) -> None:
    attrs = {"component": "pipeline", "mode": mode}
    _pipeline_sustained_compute_seconds.record(max(seconds, 0.0), attributes=attrs)
    _pipeline_sustained_key_count.record(max(float(key_count), 0.0), attributes=attrs)


def record_pipeline_case_throughput(*, case_count: int) -> None:
    _pipeline_cases_per_interval.record(
        max(float(case_count), 0.0),
        attributes={"component": "pipeline"},
    )


def record_pipeline_peak_history_scope_count(*, scope_count: int) -> None:
    with _state_lock:
        global _pipeline_peak_history_scope_count_value
        new_value = max(scope_count, 0)
        delta = new_value - _pipeline_peak_history_scope_count_value
        _pipeline_peak_history_scope_count_value = new_value
    if delta != 0:
        _pipeline_peak_history_scope_count.add(delta, attributes={"component": "pipeline"})


def record_pipeline_peak_history_evictions(*, evicted_count: int) -> None:
    if evicted_count <= 0:
        return
    _pipeline_peak_history_evictions_total.add(
        evicted_count,
        attributes={"component": "pipeline"},
    )


def record_casefile_lifecycle_purge_outcome(
    *,
    scanned_count: int,
    eligible_count: int,
    purged_count: int,
    failed_count: int,
) -> None:
    attrs = {"component": "casefile_lifecycle"}
    _casefile_lifecycle_runs_total.add(1, attributes=attrs)
    _casefile_lifecycle_objects_total.add(
        max(scanned_count, 0),
        attributes={**attrs, "outcome": "scanned"},
    )
    _casefile_lifecycle_objects_total.add(
        max(eligible_count, 0),
        attributes={**attrs, "outcome": "eligible"},
    )
    _casefile_lifecycle_objects_total.add(
        max(purged_count, 0),
        attributes={**attrs, "outcome": "purged"},
    )
    _casefile_lifecycle_objects_total.add(
        max(failed_count, 0),
        attributes={**attrs, "outcome": "failed"},
    )


def record_sn_correlation_tier(
    *,
    matched_tier: Literal["tier1", "tier2", "tier3", "none"],
) -> ServiceNowCorrelationFallbackSnapshot:
    with _state_lock:
        global _sn_correlation_total_count
        global _sn_correlation_fallback_rate_value
        global _sn_correlation_recent_fallback_sum
        if matched_tier not in _sn_correlation_tier_counts:
            raise ValueError(f"unsupported matched_tier: {matched_tier!r}")
        _sn_correlation_tier_counts[matched_tier] += 1
        _sn_correlation_total_count += 1
        fallback_flag = 1 if matched_tier in {"tier2", "tier3"} else 0
        if len(_sn_correlation_recent_fallback_flags) >= _SN_CORRELATION_RATE_WINDOW_SIZE:
            _sn_correlation_recent_fallback_sum -= _sn_correlation_recent_fallback_flags.popleft()
        _sn_correlation_recent_fallback_flags.append(fallback_flag)
        _sn_correlation_recent_fallback_sum += fallback_flag
        sample_size = len(_sn_correlation_recent_fallback_flags)
        new_rate = (
            _sn_correlation_recent_fallback_sum / sample_size
            if sample_size > 0
            else 0.0
        )
        rate_delta = new_rate - _sn_correlation_fallback_rate_value
        _sn_correlation_fallback_rate_value = new_rate

    _sn_correlation_tier_total.add(
        1,
        attributes={"component": "servicenow", "tier": matched_tier},
    )
    if rate_delta != 0:
        _sn_correlation_fallback_rate.add(
            rate_delta,
            attributes={"component": "servicenow"},
        )
    return ServiceNowCorrelationFallbackSnapshot(
        fallback_rate=new_rate,
        sample_size=sample_size,
        fallback_tiers=("tier2", "tier3"),
    )


def record_sn_page_linkage_slo(
    *,
    linkage_state: Literal["LINKED", "FAILED_FINAL"],
    within_retry_window: bool,
) -> None:
    # SLO semantics:
    # denominator = terminal PAGE linkage outcomes (LINKED/FAILED_FINAL)
    # numerator = LINKED outcomes that completed within the 2-hour retry window
    with _state_lock:
        global _sn_page_linkage_terminal_count
        global _sn_page_linkage_within_window_count
        global _sn_page_linkage_rate_value
        global _sn_page_linkage_recent_within_window_sum
        if linkage_state not in {"LINKED", "FAILED_FINAL"}:
            raise ValueError(f"unsupported linkage_state: {linkage_state!r}")
        _sn_page_linkage_terminal_count += 1
        increment_within_window = linkage_state == "LINKED" and within_retry_window
        if increment_within_window:
            _sn_page_linkage_within_window_count += 1
        within_window_flag = 1 if increment_within_window else 0
        if (
            len(_sn_page_linkage_recent_within_window_flags)
            >= _SN_PAGE_LINKAGE_RATE_WINDOW_SIZE
        ):
            _sn_page_linkage_recent_within_window_sum -= (
                _sn_page_linkage_recent_within_window_flags.popleft()
            )
        _sn_page_linkage_recent_within_window_flags.append(within_window_flag)
        _sn_page_linkage_recent_within_window_sum += within_window_flag
        sample_size = len(_sn_page_linkage_recent_within_window_flags)
        new_rate = (
            _sn_page_linkage_recent_within_window_sum / sample_size
            if sample_size > 0
            else 0.0
        )
        rate_delta = new_rate - _sn_page_linkage_rate_value
        _sn_page_linkage_rate_value = new_rate

    _sn_page_linkage_total.add(1, attributes={"component": "servicenow"})
    if increment_within_window:
        _sn_page_linkage_within_window_total.add(1, attributes={"component": "servicenow"})
    if rate_delta != 0:
        _sn_page_linkage_within_window_rate.add(
            rate_delta,
            attributes={"component": "servicenow"},
        )
