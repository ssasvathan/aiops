"""Unit tests for pipeline/stages/baseline_deviation.py — Story 2.3 (TDD RED PHASE).

These tests are written against the EXPECTED behaviour of
collect_baseline_deviation_stage_output() before the implementation exists.
They will fail with ImportError until baseline_deviation.py is created.

Test coverage:
  - Correlated finding emission (>= MIN_CORRELATED_DEVIATIONS)
  - Single-metric suppression (< MIN_CORRELATED_DEVIATIONS)
  - Suppression DEBUG log event
  - Hand-coded dedup for CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY
  - Dedup scope-exact match (other scopes still emit)
  - Per-scope error isolation (one scope raises, others proceed)
  - Fail-open on Redis unavailability (empty output returned)
  - Redis unavailable log event
  - Determinism with injected evaluation_time
  - Empty evidence output (no exceptions, empty output)
  - Finding attributes: anomaly_family, severity, is_primary
  - baseline_context populated on emitted finding
  - Stage output counters accuracy
  - reason_codes contain all deviating metrics
  - MAD returns None when bucket is too sparse → metric skipped
"""

import io
import json
import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from aiops_triage_pipeline.baseline.constants import MIN_CORRELATED_DEVIATIONS
from aiops_triage_pipeline.logging.setup import configure_logging
from aiops_triage_pipeline.models.anomaly import AnomalyDetectionResult, AnomalyFinding
from aiops_triage_pipeline.models.evidence import EvidenceRow, EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput
from aiops_triage_pipeline.pipeline.stages.baseline_deviation import (
    collect_baseline_deviation_stage_output,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXED_EVAL_TIME = datetime(2026, 4, 5, 14, 0, tzinfo=UTC)  # Sunday 14:00 UTC → bucket (6, 14)

# Historical values that produce a clear deviation when current is 5000.0:
# median ≈ 10.0, MAD = 0.0 → need some spread for MAD to work.
# Use values with spread: [8.0, 9.0, 10.0, 11.0, 12.0] → median=10, MAD=1
_STABLE_HISTORY = [8.0, 9.0, 10.0, 11.0, 12.0]  # 5 samples >= MIN_BUCKET_SAMPLES(3)
_DEVIATING_CURRENT = 5000.0  # Very far from baseline → z-score >> MAD_THRESHOLD(4.0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence_output(
    rows: list[EvidenceRow],
    findings: tuple[AnomalyFinding, ...] = (),
) -> EvidenceStageOutput:
    """Build a minimal EvidenceStageOutput for tests."""
    return EvidenceStageOutput(
        rows=tuple(rows),
        anomaly_result=AnomalyDetectionResult(findings=findings),
        gate_findings_by_scope={},
    )


def _make_peak_output() -> PeakStageOutput:
    """Build a minimal PeakStageOutput for tests."""
    return PeakStageOutput(
        profiles_by_scope={},
        classifications_by_scope={},
        peak_context_by_scope={},
        evidence_status_map_by_scope={},
        sustained_by_key={},
    )


def _make_mock_client(
    history_by_metric: dict[str, list[float]] | None = None,
) -> MagicMock:
    """Build a MagicMock SeasonalBaselineClient with configurable bucket data."""
    mock_client = MagicMock(spec=SeasonalBaselineClient)
    if history_by_metric is None:
        history_by_metric = {
            "consumer_group_lag": _STABLE_HISTORY,
            "topic_messages_in_per_sec": _STABLE_HISTORY,
        }
    mock_client.read_buckets_batch.return_value = history_by_metric
    return mock_client


def _make_deviating_row(
    scope: tuple[str, ...],
    metric_key: str,
    value: float = _DEVIATING_CURRENT,
) -> EvidenceRow:
    return EvidenceRow(metric_key=metric_key, value=value, labels={}, scope=scope)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def debug_log_stream() -> io.StringIO:
    """Configure logging at DEBUG level to capture DEBUG-level structured log events.

    Used for tests that verify events emitted at DEBUG level (e.g.
    baseline_deviation_suppressed_single_metric per AC 3 / NFR-A3).
    Scoped to the test that requests it — does not affect the shared log_stream fixture.
    """
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    configure_logging("DEBUG", log_format="json")
    return stream



# ---------------------------------------------------------------------------
# AC 1+2: Correlated finding emission (>= MIN_CORRELATED_DEVIATIONS)
# ---------------------------------------------------------------------------


def test_correlated_deviations_emit_finding() -> None:
    """Two metrics deviating on one scope → one AnomalyFinding emitted (AC 2)."""
    scope = ("prod", "kafka-prod", "orders.completed")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert len(result.findings) == 1
    assert result.findings[0].anomaly_family == "BASELINE_DEVIATION"


# ---------------------------------------------------------------------------
# AC 2: Finding attributes
# ---------------------------------------------------------------------------


def test_finding_attributes() -> None:
    """Emitted finding must have BASELINE_DEVIATION family, LOW severity, is_primary False."""
    scope = ("prod", "kafka-prod", "topic-a")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.anomaly_family == "BASELINE_DEVIATION"
    assert finding.severity == "LOW"
    assert finding.is_primary is False


def test_finding_baseline_context_populated() -> None:
    """Emitted finding must have baseline_context set (AC 2, FR15, P4)."""
    scope = ("prod", "kafka-prod", "topic-b")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert len(result.findings) == 1
    assert result.findings[0].baseline_context is not None
    ctx = result.findings[0].baseline_context
    assert ctx.metric_key is not None
    assert ctx.deviation_direction in ("HIGH", "LOW")
    assert ctx.time_bucket == (6, 14)  # Sunday 14:00 UTC


# ---------------------------------------------------------------------------
# AC 3: Single-metric suppression
# ---------------------------------------------------------------------------


def test_single_metric_suppressed() -> None:
    """Only 1 deviating metric → no finding emitted (AC 3, FR13)."""
    scope = ("prod", "kafka-prod", "lonely-topic")
    rows = [_make_deviating_row(scope, "consumer_group_lag")]
    evidence_output = _make_evidence_output(rows)
    # Return only one metric in history so only one can deviate
    mock_client = _make_mock_client({"consumer_group_lag": _STABLE_HISTORY})

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()


def test_single_metric_suppressed_log_event(debug_log_stream: io.StringIO) -> None:
    """Single-metric suppression emits DEBUG log event with scope, metric_key, reason (AC 3)."""
    scope = ("prod", "kafka-prod", "noisy-topic")
    rows = [_make_deviating_row(scope, "consumer_group_lag")]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client({"consumer_group_lag": _STABLE_HISTORY})

    collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    log_lines = [
        json.loads(line)
        for line in debug_log_stream.getvalue().splitlines()
        if line.strip() and line.strip().startswith("{")
    ]
    suppression_events = [
        ev for ev in log_lines
        if ev.get("event") == "baseline_deviation_suppressed_single_metric"
    ]
    assert len(suppression_events) >= 1
    event = suppression_events[0]
    assert "scope" in event
    assert "metric_key" in event
    assert event.get("reason") == "SINGLE_METRIC_BELOW_THRESHOLD"


# ---------------------------------------------------------------------------
# AC 4: Hand-coded dedup
# ---------------------------------------------------------------------------


def _make_hand_coded_finding(
    scope: tuple[str, ...],
    anomaly_family: str,
) -> AnomalyFinding:
    """Build a hand-coded AnomalyFinding for dedup tests."""
    scope_key = "|".join(scope)
    return AnomalyFinding(
        finding_id=f"{anomaly_family}:{scope_key}",
        anomaly_family=anomaly_family,  # type: ignore[arg-type]
        scope=scope,
        severity="HIGH",
        reason_codes=(f"{anomaly_family}_DETECTED",),
        evidence_required=("consumer_group_lag",),
        is_primary=True,
    )


def test_hand_coded_dedup_consumer_lag() -> None:
    """Scope with existing CONSUMER_LAG finding → no BASELINE_DEVIATION emitted (AC 4, FR14)."""
    scope = ("prod", "kafka-prod", "orders.completed")
    hand_coded_finding = _make_hand_coded_finding(scope, "CONSUMER_LAG")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows, findings=(hand_coded_finding,))
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()
    assert result.deviations_suppressed_dedup == 1


def test_hand_coded_dedup_volume_drop() -> None:
    """Scope with existing VOLUME_DROP finding → no BASELINE_DEVIATION emitted (AC 4, FR14)."""
    scope = ("prod", "kafka-prod", "inventory")
    hand_coded_finding = _make_hand_coded_finding(scope, "VOLUME_DROP")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows, findings=(hand_coded_finding,))
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()
    assert result.deviations_suppressed_dedup == 1


def test_hand_coded_dedup_throughput_constrained_proxy() -> None:
    """Scope with THROUGHPUT_CONSTRAINED_PROXY → no BASELINE_DEVIATION emitted (AC 4, FR14)."""
    scope = ("prod", "kafka-prod", "payments")
    hand_coded_finding = _make_hand_coded_finding(scope, "THROUGHPUT_CONSTRAINED_PROXY")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows, findings=(hand_coded_finding,))
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()
    assert result.deviations_suppressed_dedup == 1


def test_dedup_only_for_exact_scope_match() -> None:
    """Dedup suppresses scope A but scope B (no hand-coded finding) still emits (AC 4, D6)."""
    scope_a = ("prod", "kafka-prod", "topic-a")
    scope_b = ("prod", "kafka-prod", "topic-b")

    hand_coded_finding = _make_hand_coded_finding(scope_a, "CONSUMER_LAG")

    rows = [
        # Scope A: 2 deviating metrics BUT suppressed by dedup
        _make_deviating_row(scope_a, "consumer_group_lag"),
        _make_deviating_row(scope_a, "topic_messages_in_per_sec"),
        # Scope B: 2 deviating metrics, no hand-coded finding → should emit
        _make_deviating_row(scope_b, "consumer_group_lag"),
        _make_deviating_row(scope_b, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows, findings=(hand_coded_finding,))
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    # Scope B should produce one finding
    assert len(result.findings) == 1
    assert result.findings[0].scope == scope_b
    # Scope A should be suppressed
    assert result.deviations_suppressed_dedup == 1


# ---------------------------------------------------------------------------
# AC 5: Keyword-only signature + determinism
# ---------------------------------------------------------------------------


def test_determinism_injected_evaluation_time() -> None:
    """Same inputs + injected evaluation_time → identical outputs (AC 5, NFR-A4)."""
    scope = ("prod", "kafka-prod", "orders")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client()

    result_1 = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )
    result_2 = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result_1 == result_2
    assert result_1.findings[0].finding_id == result_2.findings[0].finding_id


# ---------------------------------------------------------------------------
# AC 6: Per-scope error isolation
# ---------------------------------------------------------------------------


def test_per_scope_error_isolation() -> None:
    """One scope raises exception on Redis read → remaining scopes still processed (AC 6)."""
    scope_ok = ("prod", "kafka-prod", "healthy-topic")
    scope_err = ("prod", "kafka-prod", "broken-topic")

    rows = [
        _make_deviating_row(scope_ok, "consumer_group_lag"),
        _make_deviating_row(scope_ok, "topic_messages_in_per_sec"),
        _make_deviating_row(scope_err, "consumer_group_lag"),
        _make_deviating_row(scope_err, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)

    mock_client = MagicMock(spec=SeasonalBaselineClient)

    def _side_effect(scope, metric_keys, dow, hour):  # noqa: ANN001
        if scope == scope_err:
            raise RuntimeError("Simulated Redis read failure for broken-topic")
        return {mk: _STABLE_HISTORY for mk in metric_keys}

    mock_client.read_buckets_batch.side_effect = _side_effect

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    # scope_ok should still produce a finding
    ok_findings = [f for f in result.findings if f.scope == scope_ok]
    assert len(ok_findings) == 1
    # stage does not crash
    assert result is not None


# ---------------------------------------------------------------------------
# AC 7: Fail-open on Redis unavailability
# ---------------------------------------------------------------------------


def test_redis_unavailable_fail_open() -> None:
    """Redis client raises on read → empty BaselineDeviationStageOutput returned (AC 7, NFR-R2)."""
    scope = ("prod", "kafka-prod", "topic-x")
    rows = [_make_deviating_row(scope, "consumer_group_lag")]
    evidence_output = _make_evidence_output(rows)

    mock_client = MagicMock(spec=SeasonalBaselineClient)
    mock_client.read_buckets_batch.side_effect = ConnectionError("Redis connection refused")

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()
    assert result.scopes_evaluated == 0
    assert result.deviations_detected == 0
    assert result.deviations_suppressed_single_metric == 0
    assert result.deviations_suppressed_dedup == 0


def test_redis_unavailable_log_event(log_stream) -> None:
    """Fail-open path emits baseline_deviation_redis_unavailable log event (AC 7, NFR-A3)."""
    scope = ("prod", "kafka-prod", "topic-y")
    rows = [_make_deviating_row(scope, "consumer_group_lag")]
    evidence_output = _make_evidence_output(rows)

    mock_client = MagicMock(spec=SeasonalBaselineClient)
    mock_client.read_buckets_batch.side_effect = ConnectionError("Redis connection refused")

    collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    log_lines = [
        json.loads(line)
        for line in log_stream.getvalue().splitlines()
        if line.strip()
    ]
    redis_events = [
        ev for ev in log_lines
        if ev.get("event") == "baseline_deviation_redis_unavailable"
    ]
    assert len(redis_events) >= 1


# ---------------------------------------------------------------------------
# AC 8: Empty evidence output
# ---------------------------------------------------------------------------


def test_empty_evidence_output() -> None:
    """No evidence rows → empty stage output, no exceptions (AC 8)."""
    evidence_output = _make_evidence_output([])
    mock_client = _make_mock_client({})

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()
    assert result.scopes_evaluated == 0
    assert result.deviations_detected == 0


# ---------------------------------------------------------------------------
# Stage output counters
# ---------------------------------------------------------------------------


def test_stage_output_counters() -> None:
    """Verify scopes_evaluated, deviations_detected, deviations_suppressed_* counts."""
    scope_corr = ("prod", "kafka-prod", "correlated-topic")
    scope_single = ("prod", "kafka-prod", "single-metric-topic")
    scope_dedup = ("prod", "kafka-prod", "deduped-topic")

    hand_coded = _make_hand_coded_finding(scope_dedup, "CONSUMER_LAG")

    rows = [
        # scope_corr: 2 deviating → finding emitted
        _make_deviating_row(scope_corr, "consumer_group_lag"),
        _make_deviating_row(scope_corr, "topic_messages_in_per_sec"),
        # scope_single: 1 deviating → suppressed_single_metric
        _make_deviating_row(scope_single, "consumer_group_lag"),
        # scope_dedup: 2 deviating but deduped → suppressed_dedup
        _make_deviating_row(scope_dedup, "consumer_group_lag"),
        _make_deviating_row(scope_dedup, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows, findings=(hand_coded,))

    def _history_for_scope(scope, metric_keys, dow, hour):  # noqa: ANN001
        return {mk: _STABLE_HISTORY for mk in metric_keys}

    mock_client = MagicMock(spec=SeasonalBaselineClient)
    mock_client.read_buckets_batch.side_effect = _history_for_scope

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.scopes_evaluated == 3
    assert result.deviations_suppressed_single_metric == 1
    assert result.deviations_suppressed_dedup == 1
    assert len(result.findings) == 1
    # deviations_detected counts total deviating metrics (not findings):
    # scope_corr: 2, scope_single: 1 (suppressed), scope_dedup: 2 (deduped) → 5 total
    # but deduped scope may or may not count — per story: only non-dedup scopes count toward
    # deviations_detected; dedup suppression happens after evaluation
    # deviations_detected counts deviating metrics from non-dedup scopes only:
    # scope_corr: 2 deviating metrics + scope_single: 1 deviating metric = 3 total
    # scope_dedup: skipped before _evaluate_scope (dedup takes effect first)
    assert result.deviations_detected == 3


# ---------------------------------------------------------------------------
# reason_codes contain all deviating metrics
# ---------------------------------------------------------------------------


def test_reason_codes_contain_all_deviating_metrics() -> None:
    """3 deviating metrics → 3 entries in reason_codes (story task 2.3)."""
    scope = ("prod", "kafka-prod", "multi-metric-topic")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
        _make_deviating_row(scope, "failed_produce_requests_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)

    mock_client = MagicMock(spec=SeasonalBaselineClient)
    mock_client.read_buckets_batch.return_value = {
        "consumer_group_lag": _STABLE_HISTORY,
        "topic_messages_in_per_sec": _STABLE_HISTORY,
        "failed_produce_requests_per_sec": _STABLE_HISTORY,
    }

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert len(finding.reason_codes) == 3
    # Each reason code should follow the pattern BASELINE_DEV:{metric_key}:{direction}
    for code in finding.reason_codes:
        assert code.startswith("BASELINE_DEV:")
        parts = code.split(":")
        assert len(parts) == 3
        assert parts[2] in ("HIGH", "LOW")


# ---------------------------------------------------------------------------
# MAD returns None skips metric (sparse bucket)
# ---------------------------------------------------------------------------


def test_mad_returns_none_skips_metric() -> None:
    """Metric with < MIN_BUCKET_SAMPLES history → skipped, not counted as deviation."""
    scope = ("prod", "kafka-prod", "sparse-topic")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)

    # Provide < MIN_BUCKET_SAMPLES (3) for both metrics — both should be skipped
    sparse_history = [10.0, 11.0]  # only 2 values, MIN_BUCKET_SAMPLES=3
    mock_client = _make_mock_client({
        "consumer_group_lag": sparse_history,
        "topic_messages_in_per_sec": sparse_history,
    })

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    # Both metrics skipped due to sparse history → no finding
    assert result.findings == ()


# ---------------------------------------------------------------------------
# MIN_CORRELATED_DEVIATIONS boundary: exactly 2 emits, exactly 1 suppresses
# ---------------------------------------------------------------------------


def test_exactly_min_correlated_deviations_emits_finding() -> None:
    """Exactly MIN_CORRELATED_DEVIATIONS (2) deviating metrics → finding emitted."""
    assert MIN_CORRELATED_DEVIATIONS == 2  # Sanity check constant value

    scope = ("prod", "kafka-prod", "boundary-topic")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert len(result.findings) == 1


def test_below_min_correlated_deviations_suppresses() -> None:
    """MIN_CORRELATED_DEVIATIONS - 1 (= 1) deviating metric → no finding emitted."""
    scope = ("prod", "kafka-prod", "below-threshold-topic")
    rows = [
        # Only one deviating metric (topic_messages_in_per_sec gets flat history → no deviation)
        _make_deviating_row(scope, "consumer_group_lag"),
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=10.0,  # Near baseline median of 10.0
            labels={},
            scope=scope,
        ),
    ]
    evidence_output = _make_evidence_output(rows)
    # consumer_group_lag deviates (current=5000 vs history median=10)
    # topic_messages_in_per_sec does NOT deviate (current=10 near median=10)
    mock_client = _make_mock_client({
        "consumer_group_lag": _STABLE_HISTORY,
        "topic_messages_in_per_sec": _STABLE_HISTORY,  # median≈10, current=10 → z-score≈0
    })

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert result.findings == ()
    assert result.deviations_suppressed_single_metric == 1


# ---------------------------------------------------------------------------
# Dedup log event
# ---------------------------------------------------------------------------


def test_dedup_suppression_log_event(log_stream) -> None:
    """Hand-coded dedup emits baseline_deviation_suppressed_dedup log event (AC 4, NFR-A3)."""
    scope = ("prod", "kafka-prod", "dedup-log-test")
    hand_coded = _make_hand_coded_finding(scope, "VOLUME_DROP")
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows, findings=(hand_coded,))
    mock_client = _make_mock_client()

    collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    log_lines = [
        json.loads(line)
        for line in log_stream.getvalue().splitlines()
        if line.strip()
    ]
    dedup_events = [
        ev for ev in log_lines
        if ev.get("event") == "baseline_deviation_suppressed_dedup"
    ]
    assert len(dedup_events) >= 1
    assert "scope" in dedup_events[0]


# ---------------------------------------------------------------------------
# Finding ID determinism
# ---------------------------------------------------------------------------


def test_finding_id_is_deterministic_for_scope() -> None:
    """finding_id must follow 'BASELINE_DEVIATION:{scope_key}' pattern (Dev Notes)."""
    scope = ("prod", "kafka-prod", "id-test-topic")
    scope_key = "|".join(scope)
    rows = [
        _make_deviating_row(scope, "consumer_group_lag"),
        _make_deviating_row(scope, "topic_messages_in_per_sec"),
    ]
    evidence_output = _make_evidence_output(rows)
    mock_client = _make_mock_client()

    result = collect_baseline_deviation_stage_output(
        evidence_output=evidence_output,
        peak_output=_make_peak_output(),
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )

    assert len(result.findings) == 1
    assert result.findings[0].finding_id == f"BASELINE_DEVIATION:{scope_key}"
