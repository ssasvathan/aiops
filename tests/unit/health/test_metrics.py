from __future__ import annotations

from aiops_triage_pipeline.models.health import HealthStatus


class _RecordingInstrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str] | None]] = []

    def add(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))

    def record(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))


def test_record_status_uses_delta_accounting_without_drift(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    component_status = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_component_health_gauge", component_status)
    monkeypatch.setattr(metrics, "_prev_status_values", {})

    metrics.record_status("redis", HealthStatus.HEALTHY)
    metrics.record_status("redis", HealthStatus.DEGRADED)
    metrics.record_status("redis", HealthStatus.HEALTHY)

    assert component_status.calls == [
        (0, {"component": "redis"}),
        (1, {"component": "redis"}),
        (-1, {"component": "redis"}),
    ]


def test_record_redis_connection_status_tracks_healthy_and_degraded(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    redis_connection = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_redis_connection_status", redis_connection)
    monkeypatch.setattr(metrics, "_prev_connection_values", {"redis": 1})

    metrics.record_redis_connection_status(healthy=False)
    metrics.record_redis_connection_status(healthy=True)

    assert redis_connection.calls == [
        (-1, {"component": "redis"}),
        (1, {"component": "redis"}),
    ]


def test_record_redis_dedupe_lookup_emits_hits_and_misses(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    hits = _RecordingInstrument()
    misses = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_redis_dedupe_cache_hits_total", hits)
    monkeypatch.setattr(metrics, "_redis_dedupe_cache_misses_total", misses)

    metrics.record_redis_dedupe_lookup(hit=True)
    metrics.record_redis_dedupe_lookup(hit=False)

    assert hits.calls == [(1, {"component": "redis"})]
    assert misses.calls == [(1, {"component": "redis"})]


def test_record_redis_dedupe_key_count_delta_clamps_at_zero(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    key_count = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_redis_dedupe_key_count", key_count)
    monkeypatch.setattr(metrics, "_redis_dedupe_key_count_value", 0)

    metrics.record_redis_dedupe_key_count_delta(delta=2)
    metrics.record_redis_dedupe_key_count_delta(delta=-1)
    metrics.record_redis_dedupe_key_count_delta(delta=-5)

    assert key_count.calls == [
        (2, {"component": "redis"}),
        (-1, {"component": "redis"}),
        (-1, {"component": "redis"}),
    ]


def test_record_llm_metrics_emit_expected_attributes(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    invocations = _RecordingInstrument()
    latency = _RecordingInstrument()
    timeouts = _RecordingInstrument()
    errors = _RecordingInstrument()
    fallbacks = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_llm_invocations_total", invocations)
    monkeypatch.setattr(metrics, "_llm_latency_seconds", latency)
    monkeypatch.setattr(metrics, "_llm_timeouts_total", timeouts)
    monkeypatch.setattr(metrics, "_llm_errors_total", errors)
    monkeypatch.setattr(metrics, "_llm_fallbacks_total", fallbacks)

    metrics.record_llm_invocation(result="fallback")
    metrics.record_llm_latency(seconds=-2.0, result="fallback")
    metrics.record_llm_timeout()
    metrics.record_llm_error(error_type="TimeoutError")
    metrics.record_llm_fallback(reason_code="LLM_TIMEOUT")

    assert invocations.calls == [(1, {"result": "fallback", "component": "llm"})]
    assert latency.calls == [(0.0, {"result": "fallback", "component": "llm"})]
    assert timeouts.calls == [(1, {"component": "llm"})]
    assert errors.calls == [(1, {"component": "llm", "error_type": "TimeoutError"})]
    assert fallbacks.calls == [(1, {"component": "llm", "reason_code": "LLM_TIMEOUT"})]


def test_record_prometheus_degraded_active_tracks_state_transitions(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    degraded_active = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_prometheus_degraded_active", degraded_active)
    monkeypatch.setattr(metrics, "_prometheus_degraded_active_value", 0)

    metrics.record_prometheus_degraded_active(active=True)
    metrics.record_prometheus_degraded_active(active=True)
    metrics.record_prometheus_degraded_active(active=False)

    assert degraded_active.calls == [
        (1, {"component": "prometheus"}),
        (-1, {"component": "prometheus"}),
    ]
