from __future__ import annotations

import importlib

import pytest

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


def test_record_cycle_lock_metrics_emit_expected_attributes(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    acquired = _RecordingInstrument()
    yielded = _RecordingInstrument()
    fail_open = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_coordination_cycle_lock_acquired_total", acquired)
    monkeypatch.setattr(metrics, "_coordination_cycle_lock_yielded_total", yielded)
    monkeypatch.setattr(metrics, "_coordination_cycle_lock_fail_open_total", fail_open)

    metrics.record_cycle_lock_acquired()
    metrics.record_cycle_lock_yielded()
    metrics.record_cycle_lock_fail_open(reason="redis lock acquisition failed: timeout")

    assert acquired.calls == [(1, {"component": "coordination"})]
    assert yielded.calls == [(1, {"component": "coordination"})]
    assert fail_open.calls == [
        (1, {"component": "coordination", "reason": "redis lock acquisition failed"})
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


def test_record_evidence_unknown_rate_skips_emission_when_total_count_is_zero(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    unknown_rate = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_evidence_unknown_rate", unknown_rate)

    metrics.record_evidence_unknown_rate(
        metric_key="topic_messages_in_per_sec",
        unknown_count=0,
        total_count=0,
    )

    assert unknown_rate.calls == []


def test_record_sustained_compute_metrics_emit_duration_and_key_count(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    sustained_duration = _RecordingInstrument()
    sustained_key_count = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_pipeline_sustained_compute_seconds", sustained_duration)
    monkeypatch.setattr(metrics, "_pipeline_sustained_key_count", sustained_key_count)

    metrics.record_pipeline_sustained_compute(
        seconds=0.125,
        key_count=42,
        mode="parallel",
    )

    assert sustained_duration.calls == [
        (0.125, {"component": "pipeline", "mode": "parallel"}),
    ]
    assert sustained_key_count.calls == [
        (42.0, {"component": "pipeline", "mode": "parallel"}),
    ]


def test_record_peak_history_metrics_track_scope_count_and_evictions(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    scope_count = _RecordingInstrument()
    evictions = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_pipeline_peak_history_scope_count", scope_count)
    monkeypatch.setattr(metrics, "_pipeline_peak_history_evictions_total", evictions)
    monkeypatch.setattr(metrics, "_pipeline_peak_history_scope_count_value", 0)

    metrics.record_pipeline_peak_history_scope_count(scope_count=3)
    metrics.record_pipeline_peak_history_scope_count(scope_count=1)
    metrics.record_pipeline_peak_history_evictions(evicted_count=2)

    assert scope_count.calls == [
        (3, {"component": "pipeline"}),
        (-2, {"component": "pipeline"}),
    ]
    assert evictions.calls == [(2, {"component": "pipeline"})]


def test_record_casefile_lifecycle_purge_outcome_emits_run_and_object_counts(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics as metrics_module

    metrics = importlib.reload(metrics_module)

    runs_total = _RecordingInstrument()
    objects_total = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_casefile_lifecycle_runs_total", runs_total)
    monkeypatch.setattr(metrics, "_casefile_lifecycle_objects_total", objects_total)

    metrics.record_casefile_lifecycle_purge_outcome(
        scanned_count=7,
        eligible_count=3,
        purged_count=2,
        failed_count=1,
    )

    assert runs_total.calls == [(1, {"component": "casefile_lifecycle"})]
    assert objects_total.calls == [
        (7, {"component": "casefile_lifecycle", "outcome": "scanned"}),
        (3, {"component": "casefile_lifecycle", "outcome": "eligible"}),
        (2, {"component": "casefile_lifecycle", "outcome": "purged"}),
        (1, {"component": "casefile_lifecycle", "outcome": "failed"}),
    ]


def test_record_sn_correlation_tier_tracks_tier_counts_and_fallback_rate(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    tier_total = _RecordingInstrument()
    fallback_rate = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_sn_correlation_tier_total", tier_total)
    monkeypatch.setattr(metrics, "_sn_correlation_fallback_rate", fallback_rate)
    monkeypatch.setattr(
        metrics,
        "_sn_correlation_tier_counts",
        {
            "tier1": 0,
            "tier2": 0,
            "tier3": 0,
            "none": 0,
        },
    )
    monkeypatch.setattr(metrics, "_sn_correlation_total_count", 0)
    monkeypatch.setattr(metrics, "_sn_correlation_fallback_rate_value", 0.0)
    monkeypatch.setattr(metrics, "_sn_correlation_recent_fallback_flags", metrics.deque())
    monkeypatch.setattr(metrics, "_sn_correlation_recent_fallback_sum", 0)
    monkeypatch.setattr(metrics, "_SN_CORRELATION_RATE_WINDOW_SIZE", 120)

    metrics.record_sn_correlation_tier(matched_tier="tier2")
    metrics.record_sn_correlation_tier(matched_tier="tier1")
    metrics.record_sn_correlation_tier(matched_tier="tier3")
    metrics.record_sn_correlation_tier(matched_tier="none")

    assert tier_total.calls == [
        (1, {"component": "servicenow", "tier": "tier2"}),
        (1, {"component": "servicenow", "tier": "tier1"}),
        (1, {"component": "servicenow", "tier": "tier3"}),
        (1, {"component": "servicenow", "tier": "none"}),
    ]
    assert fallback_rate.calls[0] == (1.0, {"component": "servicenow"})
    assert fallback_rate.calls[1] == (-0.5, {"component": "servicenow"})
    assert fallback_rate.calls[2][1] == {"component": "servicenow"}
    assert fallback_rate.calls[2][0] == pytest.approx(1 / 6)
    assert fallback_rate.calls[3][1] == {"component": "servicenow"}
    assert fallback_rate.calls[3][0] == pytest.approx(-1 / 6)


def test_record_sn_page_linkage_slo_tracks_totals_and_rate(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    page_total = _RecordingInstrument()
    within_window_total = _RecordingInstrument()
    within_window_rate = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_sn_page_linkage_total", page_total)
    monkeypatch.setattr(metrics, "_sn_page_linkage_within_window_total", within_window_total)
    monkeypatch.setattr(metrics, "_sn_page_linkage_within_window_rate", within_window_rate)
    monkeypatch.setattr(metrics, "_sn_page_linkage_terminal_count", 0)
    monkeypatch.setattr(metrics, "_sn_page_linkage_within_window_count", 0)
    monkeypatch.setattr(metrics, "_sn_page_linkage_rate_value", 0.0)
    monkeypatch.setattr(metrics, "_sn_page_linkage_recent_within_window_flags", metrics.deque())
    monkeypatch.setattr(metrics, "_sn_page_linkage_recent_within_window_sum", 0)
    monkeypatch.setattr(metrics, "_SN_PAGE_LINKAGE_RATE_WINDOW_SIZE", 120)

    metrics.record_sn_page_linkage_slo(linkage_state="LINKED", within_retry_window=True)
    metrics.record_sn_page_linkage_slo(linkage_state="FAILED_FINAL", within_retry_window=False)
    metrics.record_sn_page_linkage_slo(linkage_state="LINKED", within_retry_window=False)

    assert page_total.calls == [
        (1, {"component": "servicenow"}),
        (1, {"component": "servicenow"}),
        (1, {"component": "servicenow"}),
    ]
    assert within_window_total.calls == [(1, {"component": "servicenow"})]
    assert within_window_rate.calls[0] == (1.0, {"component": "servicenow"})
    assert within_window_rate.calls[1] == (-0.5, {"component": "servicenow"})
    assert within_window_rate.calls[2][1] == {"component": "servicenow"}
    assert within_window_rate.calls[2][0] == pytest.approx(-1 / 6)


def test_record_sn_correlation_tier_uses_rolling_window_for_rate(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    fallback_rate = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_sn_correlation_fallback_rate", fallback_rate)
    monkeypatch.setattr(metrics, "_sn_correlation_tier_total", _RecordingInstrument())
    monkeypatch.setattr(
        metrics,
        "_sn_correlation_tier_counts",
        {"tier1": 0, "tier2": 0, "tier3": 0, "none": 0},
    )
    monkeypatch.setattr(metrics, "_sn_correlation_total_count", 0)
    monkeypatch.setattr(metrics, "_sn_correlation_fallback_rate_value", 0.0)
    monkeypatch.setattr(metrics, "_sn_correlation_recent_fallback_flags", metrics.deque())
    monkeypatch.setattr(metrics, "_sn_correlation_recent_fallback_sum", 0)
    monkeypatch.setattr(metrics, "_SN_CORRELATION_RATE_WINDOW_SIZE", 3)

    metrics.record_sn_correlation_tier(matched_tier="tier2")
    metrics.record_sn_correlation_tier(matched_tier="tier2")
    metrics.record_sn_correlation_tier(matched_tier="tier1")
    snapshot = metrics.record_sn_correlation_tier(matched_tier="tier1")

    assert snapshot.sample_size == 3
    assert snapshot.fallback_rate == pytest.approx(1 / 3)
    assert len(fallback_rate.calls) == 3
    assert fallback_rate.calls[0] == (1.0, {"component": "servicenow"})
    assert fallback_rate.calls[1][1] == {"component": "servicenow"}
    assert fallback_rate.calls[1][0] == pytest.approx(-1 / 3)
    assert fallback_rate.calls[2][1] == {"component": "servicenow"}
    assert fallback_rate.calls[2][0] == pytest.approx(-1 / 3)


def test_record_sn_page_linkage_slo_uses_rolling_window_for_rate(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    within_window_rate = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_sn_page_linkage_total", _RecordingInstrument())
    monkeypatch.setattr(metrics, "_sn_page_linkage_within_window_total", _RecordingInstrument())
    monkeypatch.setattr(metrics, "_sn_page_linkage_within_window_rate", within_window_rate)
    monkeypatch.setattr(metrics, "_sn_page_linkage_terminal_count", 0)
    monkeypatch.setattr(metrics, "_sn_page_linkage_within_window_count", 0)
    monkeypatch.setattr(metrics, "_sn_page_linkage_rate_value", 0.0)
    monkeypatch.setattr(metrics, "_sn_page_linkage_recent_within_window_flags", metrics.deque())
    monkeypatch.setattr(metrics, "_sn_page_linkage_recent_within_window_sum", 0)
    monkeypatch.setattr(metrics, "_SN_PAGE_LINKAGE_RATE_WINDOW_SIZE", 2)

    metrics.record_sn_page_linkage_slo(linkage_state="LINKED", within_retry_window=True)
    metrics.record_sn_page_linkage_slo(linkage_state="FAILED_FINAL", within_retry_window=False)
    metrics.record_sn_page_linkage_slo(linkage_state="FAILED_FINAL", within_retry_window=False)

    assert within_window_rate.calls == [
        (1.0, {"component": "servicenow"}),
        (-0.5, {"component": "servicenow"}),
        (-0.5, {"component": "servicenow"}),
    ]
