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


# ---------------------------------------------------------------------------
# Story 1.2: Findings & Gating OTLP Instruments — ATDD Red Phase
# AC1: aiops.findings.total counter — name, labels, uppercase values
# AC2: aiops.gating.evaluations_total counter — name, labels
# AC3: instruments defined in health/metrics.py using create_counter
# AC4: tests assert on metric name + label set (not raw string output)
# ---------------------------------------------------------------------------


# AC1 / AC4 — P0
def test_record_finding_emits_expected_metric_name_and_labels(monkeypatch) -> None:
    """aiops.findings.total increments by 1 with all five required labels (AC1, AC4)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_findings_total", counter)

    metrics.record_finding(
        anomaly_family="BASELINE_DEVIATION",
        final_action="NOTIFY",
        topic="payments.consumer-lag",
        routing_key="payments-team",
        criticality_tier="TIER_0",
    )

    assert len(counter.calls) == 1
    value, attributes = counter.calls[0]
    assert value == 1
    assert attributes == {
        "anomaly_family": "BASELINE_DEVIATION",
        "final_action": "NOTIFY",
        "topic": "payments.consumer-lag",
        "routing_key": "payments-team",
        "criticality_tier": "TIER_0",
    }


# AC1 / AC4 — P0: uppercase label values
def test_record_finding_emits_uppercase_label_values(monkeypatch) -> None:
    """Label values must be uppercase as-is from enum contracts — no lowercasing (AC1)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_findings_total", counter)

    metrics.record_finding(
        anomaly_family="CONSUMER_LAG",
        final_action="PAGE",
        topic="payments.consumer-lag",
        routing_key="sre-team",
        criticality_tier="TIER_1",
    )

    _, attributes = counter.calls[0]
    assert attributes["anomaly_family"] == "CONSUMER_LAG"
    assert attributes["final_action"] == "PAGE"
    assert attributes["criticality_tier"] == "TIER_1"


# AC1 / AC4 — P0: all four Action enum values
def test_record_finding_accepts_all_action_values(monkeypatch) -> None:
    """record_finding works for all Action enum values: OBSERVE, NOTIFY, TICKET, PAGE (AC1)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_findings_total", counter)

    for action in ("OBSERVE", "NOTIFY", "TICKET", "PAGE"):
        metrics.record_finding(
            anomaly_family="VOLUME_DROP",
            final_action=action,
            topic="inventory.lag",
            routing_key="inventory-team",
            criticality_tier="TIER_0",
        )

    assert len(counter.calls) == 4
    emitted_actions = [attrs["final_action"] for _, attrs in counter.calls]
    assert emitted_actions == ["OBSERVE", "NOTIFY", "TICKET", "PAGE"]


# AC1 / AC4 — P1: multiple calls accumulate independently
def test_record_finding_multiple_calls_each_emit_independently(monkeypatch) -> None:
    """Each call to record_finding emits one independent increment (AC1, NFR8)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_findings_total", counter)

    metrics.record_finding(
        anomaly_family="BASELINE_DEVIATION",
        final_action="NOTIFY",
        topic="payments.consumer-lag",
        routing_key="payments-team",
        criticality_tier="TIER_0",
    )
    metrics.record_finding(
        anomaly_family="THROUGHPUT_CONSTRAINED_PROXY",
        final_action="TICKET",
        topic="gateway.throughput",
        routing_key="platform-team",
        criticality_tier="TIER_1",
    )

    assert len(counter.calls) == 2
    assert counter.calls[0] == (
        1,
        {
            "anomaly_family": "BASELINE_DEVIATION",
            "final_action": "NOTIFY",
            "topic": "payments.consumer-lag",
            "routing_key": "payments-team",
            "criticality_tier": "TIER_0",
        },
    )
    assert counter.calls[1] == (
        1,
        {
            "anomaly_family": "THROUGHPUT_CONSTRAINED_PROXY",
            "final_action": "TICKET",
            "topic": "gateway.throughput",
            "routing_key": "platform-team",
            "criticality_tier": "TIER_1",
        },
    )


# AC2 / AC4 — P0
def test_record_gating_evaluation_emits_expected_metric_name_and_labels(monkeypatch) -> None:
    """aiops.gating.evaluations_total increments by 1 with gate_id, outcome, topic (AC2, AC4)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_gating_evaluations_total", counter)

    metrics.record_gating_evaluation(
        gate_id="AG0",
        outcome="pass",
        topic="payments.consumer-lag",
    )

    assert len(counter.calls) == 1
    value, attributes = counter.calls[0]
    assert value == 1
    assert attributes == {
        "gate_id": "AG0",
        "outcome": "pass",
        "topic": "payments.consumer-lag",
    }


# AC2 / AC4 — P0: fail and skip outcomes
def test_record_gating_evaluation_accepts_fail_and_skip_outcomes(monkeypatch) -> None:
    """record_gating_evaluation handles 'pass', 'fail', and 'skip' outcomes (AC2)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_gating_evaluations_total", counter)

    metrics.record_gating_evaluation(gate_id="AG1", outcome="pass", topic="topic-a")
    metrics.record_gating_evaluation(gate_id="AG2", outcome="fail", topic="topic-a")
    metrics.record_gating_evaluation(gate_id="AG3", outcome="skip", topic="topic-a")

    assert len(counter.calls) == 3
    outcomes = [attrs["outcome"] for _, attrs in counter.calls]
    assert outcomes == ["pass", "fail", "skip"]


# AC2 — P1: routing_key must NOT appear in gating labels
def test_record_gating_evaluation_does_not_include_routing_key_label(monkeypatch) -> None:
    """aiops.gating.evaluations_total labels: gate_id, outcome, topic — no routing_key (AC2)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_gating_evaluations_total", counter)

    metrics.record_gating_evaluation(
        gate_id="AG4",
        outcome="pass",
        topic="payments.consumer-lag",
    )

    _, attributes = counter.calls[0]
    assert "routing_key" not in attributes
    assert set(attributes.keys()) == {"gate_id", "outcome", "topic"}


# AC2 — P1: topic label is present for every gate ID in _EXPECTED_GATE_ORDER
def test_record_gating_evaluation_emits_topic_for_all_gate_ids(monkeypatch) -> None:
    """topic label is available and emitted for all known gate IDs AG0–AG6 (AC2)."""
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_gating_evaluations_total", counter)

    gate_ids = ["AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6"]
    for gate_id in gate_ids:
        metrics.record_gating_evaluation(
            gate_id=gate_id,
            outcome="pass",
            topic="test-topic",
        )

    assert len(counter.calls) == len(gate_ids)
    for (_, attrs), gate_id in zip(counter.calls, gate_ids):
        assert attrs["gate_id"] == gate_id
        assert "topic" in attrs


# AC3 — P0: _findings_total instrument exists and is a counter (not up_down_counter)
def test_findings_total_instrument_is_defined_in_metrics_module() -> None:
    """_findings_total must be a module-level counter defined via create_counter (AC3)."""
    from aiops_triage_pipeline.health import metrics

    assert hasattr(metrics, "_findings_total"), (
        "_findings_total counter not found in health/metrics.py"
    )
    # The instrument must have an .add() method (counter interface)
    assert callable(getattr(metrics._findings_total, "add", None)), (
        "_findings_total must be a Counter with .add() method"
    )


# AC3 — P0: _gating_evaluations_total instrument exists and is a counter
def test_gating_evaluations_total_instrument_is_defined_in_metrics_module() -> None:
    """_gating_evaluations_total must be a module-level counter defined via create_counter (AC3)."""
    from aiops_triage_pipeline.health import metrics

    assert hasattr(metrics, "_gating_evaluations_total"), (
        "_gating_evaluations_total counter not found in health/metrics.py"
    )
    assert callable(getattr(metrics._gating_evaluations_total, "add", None)), (
        "_gating_evaluations_total must be a Counter with .add() method"
    )


# AC3 — P0: public functions are callable
def test_record_finding_function_is_callable() -> None:
    """record_finding public function must exist and be callable (AC3)."""
    from aiops_triage_pipeline.health import metrics

    assert callable(getattr(metrics, "record_finding", None)), (
        "record_finding() not found in health/metrics.py"
    )


# AC3 — P0: public functions are callable
def test_record_gating_evaluation_function_is_callable() -> None:
    """record_gating_evaluation public function must exist and be callable (AC3)."""
    from aiops_triage_pipeline.health import metrics

    assert callable(getattr(metrics, "record_gating_evaluation", None)), (
        "record_gating_evaluation() not found in health/metrics.py"
    )
