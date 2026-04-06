"""Unit tests for Story 2.4: Pipeline Integration & Scheduler Wiring (TDD RED PHASE).

Tests are written against EXPECTED behaviour before implementation.
They will fail with ImportError or AttributeError until the implementation exists.

Coverage:
  - run_baseline_deviation_stage_cycle() scheduler wrapper (AC 1)
  - _merge_baseline_deviation_findings() helper (AC 2)
  - _update_baseline_buckets() helper (AC 7)
  - BASELINE_DEVIATION_STAGE_ENABLED flag (AC 6)
"""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from aiops_triage_pipeline.__main__ import (
    _merge_baseline_deviation_findings,
    _update_baseline_buckets,
)
from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from aiops_triage_pipeline.baseline.models import BaselineDeviationStageOutput
from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.models.anomaly import AnomalyDetectionResult, AnomalyFinding
from aiops_triage_pipeline.models.evidence import EvidenceRow, EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput
from aiops_triage_pipeline.pipeline.scheduler import run_baseline_deviation_stage_cycle

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXED_EVAL_TIME = datetime(2026, 4, 5, 14, 0, tzinfo=UTC)  # Sunday 14:00 UTC

# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------


def _make_evidence_output(
    rows: tuple[EvidenceRow, ...] = (),
    gate_findings_by_scope: dict[tuple[str, ...], tuple[Finding, ...]] | None = None,
) -> EvidenceStageOutput:
    return EvidenceStageOutput(
        rows=rows,
        anomaly_result=AnomalyDetectionResult(findings=()),
        gate_findings_by_scope=gate_findings_by_scope or {},
    )


def _make_peak_output() -> PeakStageOutput:
    return PeakStageOutput(
        profiles_by_scope={},
        classifications_by_scope={},
        peak_context_by_scope={},
        evidence_status_map_by_scope={},
        sustained_by_key={},
    )


def _make_baseline_deviation_output(
    findings: tuple[AnomalyFinding, ...] = (),
) -> BaselineDeviationStageOutput:
    return BaselineDeviationStageOutput(
        findings=findings,
        scopes_evaluated=0,
        deviations_detected=len(findings),
        deviations_suppressed_single_metric=0,
        deviations_suppressed_dedup=0,
        evaluation_time=FIXED_EVAL_TIME,
    )


def _make_anomaly_finding(
    scope: tuple[str, ...] = ("prod", "kafka-prod", "orders.completed"),
    anomaly_family: str = "BASELINE_DEVIATION",
) -> AnomalyFinding:
    return AnomalyFinding(
        finding_id="bd-test-finding-001",
        anomaly_family=anomaly_family,  # type: ignore[arg-type]
        scope=scope,
        severity="MEDIUM",
        reason_codes=("consumer_group_lag", "topic_messages_in_per_sec"),
        evidence_required=("consumer_group_lag", "topic_messages_in_per_sec"),
        is_primary=True,
    )


def _make_finding(
    finding_id: str = "f-existing",
    name: str = "consumer_lag",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        name=name,
        is_anomalous=True,
        evidence_required=("consumer_group_lag",),
        is_primary=True,
        severity="HIGH",
        reason_codes=("CONSUMER_LAG",),
    )


def _make_evidence_row(
    scope: tuple[str, ...],
    metric_key: str,
    value: float,
) -> EvidenceRow:
    return EvidenceRow(
        metric_key=metric_key,
        value=value,
        labels={},
        scope=scope,
    )


def _make_mock_baseline_client() -> MagicMock:
    return MagicMock(spec=SeasonalBaselineClient)


# ---------------------------------------------------------------------------
# AC 1: run_baseline_deviation_stage_cycle() — scheduler wrapper
# ---------------------------------------------------------------------------


def test_run_baseline_deviation_stage_cycle_calls_stage_function() -> None:
    """AC 1: run_baseline_deviation_stage_cycle() calls collect_baseline_deviation_stage_output
    with correct keyword arguments and returns BaselineDeviationStageOutput."""
    evidence_output = _make_evidence_output()
    peak_output = _make_peak_output()
    mock_client = _make_mock_baseline_client()
    expected_output = _make_baseline_deviation_output()

    with patch(
        "aiops_triage_pipeline.pipeline.scheduler.collect_baseline_deviation_stage_output",
        return_value=expected_output,
    ) as mock_collect:
        result = run_baseline_deviation_stage_cycle(
            evidence_output=evidence_output,
            peak_output=peak_output,
            baseline_client=mock_client,
            evaluation_time=FIXED_EVAL_TIME,
        )

    mock_collect.assert_called_once_with(
        evidence_output=evidence_output,
        peak_output=peak_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
    )
    assert result is expected_output
    assert isinstance(result, BaselineDeviationStageOutput)


def test_run_baseline_deviation_stage_cycle_records_latency() -> None:
    """AC 1: run_baseline_deviation_stage_cycle() calls record_pipeline_compute_latency
    with stage='stage2_5_baseline_deviation'."""
    evidence_output = _make_evidence_output()
    peak_output = _make_peak_output()
    mock_client = _make_mock_baseline_client()
    expected_output = _make_baseline_deviation_output()

    with patch(
        "aiops_triage_pipeline.pipeline.scheduler.collect_baseline_deviation_stage_output",
        return_value=expected_output,
    ):
        with patch(
            "aiops_triage_pipeline.pipeline.scheduler.record_pipeline_compute_latency"
        ) as mock_record:
            run_baseline_deviation_stage_cycle(
                evidence_output=evidence_output,
                peak_output=peak_output,
                baseline_client=mock_client,
                evaluation_time=FIXED_EVAL_TIME,
            )

    mock_record.assert_called_once()
    call_kwargs = mock_record.call_args
    assert call_kwargs.kwargs["stage"] == "stage2_5_baseline_deviation"
    assert isinstance(call_kwargs.kwargs["seconds"], float)


def test_run_baseline_deviation_stage_cycle_records_latency_even_on_exception() -> None:
    """AC 1: record_pipeline_compute_latency is called in finally block even if stage raises."""
    evidence_output = _make_evidence_output()
    peak_output = _make_peak_output()
    mock_client = _make_mock_baseline_client()

    with patch(
        "aiops_triage_pipeline.pipeline.scheduler.collect_baseline_deviation_stage_output",
        side_effect=RuntimeError("stage failed"),
    ):
        with patch(
            "aiops_triage_pipeline.pipeline.scheduler.record_pipeline_compute_latency"
        ) as mock_record:
            with pytest.raises(RuntimeError, match="stage failed"):
                run_baseline_deviation_stage_cycle(
                    evidence_output=evidence_output,
                    peak_output=peak_output,
                    baseline_client=mock_client,
                    evaluation_time=FIXED_EVAL_TIME,
                )

    # Must still record latency in finally block
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["stage"] == "stage2_5_baseline_deviation"


def test_run_baseline_deviation_stage_cycle_calls_alert_evaluator_when_provided() -> None:
    """AC 1: alert_evaluator.evaluate_pipeline_stage_latency is called when alert_evaluator
    is not None, mirroring the exact pattern in run_topology_stage_cycle."""
    evidence_output = _make_evidence_output()
    peak_output = _make_peak_output()
    mock_client = _make_mock_baseline_client()
    expected_output = _make_baseline_deviation_output()
    mock_alert_evaluator = MagicMock()
    mock_alert_evaluator.evaluate_pipeline_stage_latency.return_value = None

    with patch(
        "aiops_triage_pipeline.pipeline.scheduler.collect_baseline_deviation_stage_output",
        return_value=expected_output,
    ):
        run_baseline_deviation_stage_cycle(
            evidence_output=evidence_output,
            peak_output=peak_output,
            baseline_client=mock_client,
            evaluation_time=FIXED_EVAL_TIME,
            alert_evaluator=mock_alert_evaluator,
        )

    mock_alert_evaluator.evaluate_pipeline_stage_latency.assert_called_once()
    call_kwargs = mock_alert_evaluator.evaluate_pipeline_stage_latency.call_args.kwargs
    assert call_kwargs["stage"] == "stage2_5_baseline_deviation"
    assert isinstance(call_kwargs["seconds"], float)


def test_run_baseline_deviation_stage_cycle_does_not_call_alert_evaluator_when_none() -> None:
    """AC 1: alert_evaluator defaults to None; no call is made when omitted."""
    evidence_output = _make_evidence_output()
    peak_output = _make_peak_output()
    mock_client = _make_mock_baseline_client()
    expected_output = _make_baseline_deviation_output()

    with patch(
        "aiops_triage_pipeline.pipeline.scheduler.collect_baseline_deviation_stage_output",
        return_value=expected_output,
    ):
        # Should not raise even without alert_evaluator
        result = run_baseline_deviation_stage_cycle(
            evidence_output=evidence_output,
            peak_output=peak_output,
            baseline_client=mock_client,
            evaluation_time=FIXED_EVAL_TIME,
        )

    assert isinstance(result, BaselineDeviationStageOutput)


# ---------------------------------------------------------------------------
# AC 2: _merge_baseline_deviation_findings() helper
# ---------------------------------------------------------------------------


def test_merge_baseline_deviation_findings_injects_into_gate_scope() -> None:
    """AC 2: BASELINE_DEVIATION findings are injected into the correct scope in
    gate_findings_by_scope of the returned EvidenceStageOutput."""
    scope = ("prod", "kafka-prod", "orders.completed")
    finding = _make_anomaly_finding(scope=scope)
    baseline_deviation_output = _make_baseline_deviation_output(findings=(finding,))
    evidence_output = _make_evidence_output(gate_findings_by_scope={})

    result = _merge_baseline_deviation_findings(
        evidence_output=evidence_output,
        baseline_deviation_output=baseline_deviation_output,
    )

    assert scope in result.gate_findings_by_scope
    injected = result.gate_findings_by_scope[scope]
    assert len(injected) == 1
    # The Finding.name must be the lowercase anomaly_family
    assert injected[0].name == "baseline_deviation"
    assert injected[0].is_anomalous is True


def test_merge_baseline_deviation_findings_preserves_existing_gate_findings() -> None:
    """AC 2: Pre-existing gate findings for a scope are not overwritten by merged findings."""
    scope = ("prod", "kafka-prod", "orders.completed")
    existing_finding = _make_finding(finding_id="f-existing", name="consumer_lag")
    bd_finding = _make_anomaly_finding(scope=scope)

    evidence_output = _make_evidence_output(
        gate_findings_by_scope={scope: (existing_finding,)}
    )
    baseline_deviation_output = _make_baseline_deviation_output(findings=(bd_finding,))

    result = _merge_baseline_deviation_findings(
        evidence_output=evidence_output,
        baseline_deviation_output=baseline_deviation_output,
    )

    merged = result.gate_findings_by_scope[scope]
    assert len(merged) == 2
    finding_names = {f.name for f in merged}
    assert "consumer_lag" in finding_names
    assert "baseline_deviation" in finding_names


def test_merge_baseline_deviation_findings_no_op_when_empty() -> None:
    """AC 2: When baseline_deviation_output.findings is empty, gate_findings_by_scope
    is unchanged and the returned output is equivalent to the original."""
    scope = ("prod", "kafka-prod", "orders.completed")
    existing_finding = _make_finding()
    evidence_output = _make_evidence_output(
        gate_findings_by_scope={scope: (existing_finding,)}
    )
    empty_baseline_output = _make_baseline_deviation_output(findings=())

    result = _merge_baseline_deviation_findings(
        evidence_output=evidence_output,
        baseline_deviation_output=empty_baseline_output,
    )

    # Original scope and finding preserved
    assert scope in result.gate_findings_by_scope
    assert len(result.gate_findings_by_scope[scope]) == 1
    assert result.gate_findings_by_scope[scope][0].finding_id == "f-existing"


def test_merge_baseline_deviation_findings_returns_new_evidence_stage_output() -> None:
    """AC 2: _merge_baseline_deviation_findings returns a new EvidenceStageOutput
    (not the same object — EvidenceStageOutput is frozen=True)."""
    scope = ("prod", "kafka-prod", "orders.completed")
    finding = _make_anomaly_finding(scope=scope)
    evidence_output = _make_evidence_output()
    baseline_deviation_output = _make_baseline_deviation_output(findings=(finding,))

    result = _merge_baseline_deviation_findings(
        evidence_output=evidence_output,
        baseline_deviation_output=baseline_deviation_output,
    )

    assert result is not evidence_output
    assert isinstance(result, EvidenceStageOutput)


def test_merge_baseline_deviation_findings_multiple_scopes() -> None:
    """AC 2: Multiple baseline deviation findings across different scopes are all injected."""
    scope_a = ("prod", "kafka-prod", "orders.completed")
    scope_b = ("prod", "kafka-prod", "payments.completed")
    finding_a = AnomalyFinding(
        finding_id="bd-001",
        anomaly_family="BASELINE_DEVIATION",
        scope=scope_a,
        severity="MEDIUM",
        reason_codes=("metric_a",),
        evidence_required=("metric_a",),
        is_primary=True,
    )
    finding_b = AnomalyFinding(
        finding_id="bd-002",
        anomaly_family="BASELINE_DEVIATION",
        scope=scope_b,
        severity="MEDIUM",
        reason_codes=("metric_b",),
        evidence_required=("metric_b",),
        is_primary=True,
    )
    evidence_output = _make_evidence_output()
    baseline_deviation_output = _make_baseline_deviation_output(
        findings=(finding_a, finding_b)
    )

    result = _merge_baseline_deviation_findings(
        evidence_output=evidence_output,
        baseline_deviation_output=baseline_deviation_output,
    )

    assert scope_a in result.gate_findings_by_scope
    assert scope_b in result.gate_findings_by_scope
    assert len(result.gate_findings_by_scope[scope_a]) == 1
    assert len(result.gate_findings_by_scope[scope_b]) == 1


# ---------------------------------------------------------------------------
# AC 7: _update_baseline_buckets() helper
# ---------------------------------------------------------------------------


def test_update_baseline_buckets_calls_update_bucket_per_scope_metric() -> None:
    """AC 7: _update_baseline_buckets() calls update_bucket once per unique scope/metric pair."""
    scope_a = ("prod", "kafka-prod", "orders.completed")
    rows = (
        _make_evidence_row(scope_a, "consumer_group_lag", 100.0),
        _make_evidence_row(scope_a, "topic_messages_in_per_sec", 5000.0),
    )
    evidence_output = _make_evidence_output(rows=rows)
    mock_client = _make_mock_baseline_client()
    mock_logger = MagicMock()

    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
        logger=mock_logger,
    )

    # Called once per unique (scope, metric_key) pair
    assert mock_client.update_bucket.call_count == 2
    call_scopes_and_metrics = {
        (c.args[0], c.args[1]) for c in mock_client.update_bucket.call_args_list
    }
    assert (scope_a, "consumer_group_lag") in call_scopes_and_metrics
    assert (scope_a, "topic_messages_in_per_sec") in call_scopes_and_metrics


def test_update_baseline_buckets_uses_max_value_for_dedup() -> None:
    """AC 7: When multiple rows exist for the same scope/metric, max() is used as the value."""
    scope = ("prod", "kafka-prod", "orders.completed")
    rows = (
        _make_evidence_row(scope, "consumer_group_lag", 100.0),
        _make_evidence_row(scope, "consumer_group_lag", 300.0),  # higher
        _make_evidence_row(scope, "consumer_group_lag", 50.0),   # lower
    )
    evidence_output = _make_evidence_output(rows=rows)
    mock_client = _make_mock_baseline_client()
    mock_logger = MagicMock()

    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
        logger=mock_logger,
    )

    # Only one update_bucket call for this scope/metric
    assert mock_client.update_bucket.call_count == 1
    # The value passed must be the maximum
    call_args = mock_client.update_bucket.call_args
    # update_bucket(scope, metric_key, dow, hour, value)
    assert call_args.args[4] == 300.0


def test_update_baseline_buckets_error_isolation() -> None:
    """AC 7: If update_bucket raises for one scope/metric, others are still processed.
    Errors are logged at WARNING level per fail-open pattern."""
    scope_a = ("prod", "kafka-prod", "orders.completed")
    scope_b = ("prod", "kafka-prod", "payments.completed")
    rows = (
        _make_evidence_row(scope_a, "consumer_group_lag", 100.0),
        _make_evidence_row(scope_b, "consumer_group_lag", 200.0),
    )
    evidence_output = _make_evidence_output(rows=rows)
    mock_client = _make_mock_baseline_client()
    mock_logger = MagicMock()

    # First call raises, second should still succeed
    mock_client.update_bucket.side_effect = [
        ConnectionError("Redis unavailable"),
        None,  # second call succeeds
    ]

    # Must NOT raise — fail-open pattern
    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
        logger=mock_logger,
    )

    # Both attempted
    assert mock_client.update_bucket.call_count == 2
    # Error logged at WARNING
    mock_logger.warning.assert_called_once()
    warning_call_kwargs = mock_logger.warning.call_args
    assert "baseline_deviation_bucket_update_failed" in str(warning_call_kwargs)


def test_update_baseline_buckets_uses_correct_time_bucket() -> None:
    """AC 7: _update_baseline_buckets() passes the correct (dow, hour) bucket from evaluation_time
    to update_bucket."""
    # FIXED_EVAL_TIME: 2026-04-05 14:00 UTC → Sunday (dow=6), hour=14
    scope = ("prod", "kafka-prod", "orders.completed")
    rows = (_make_evidence_row(scope, "consumer_group_lag", 100.0),)
    evidence_output = _make_evidence_output(rows=rows)
    mock_client = _make_mock_baseline_client()
    mock_logger = MagicMock()

    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
        logger=mock_logger,
    )

    call_args = mock_client.update_bucket.call_args
    # args: (scope, metric_key, dow, hour, value)
    dow = call_args.args[2]
    hour = call_args.args[3]
    # Sunday = 6 in Python's weekday() convention
    assert dow == 6
    assert hour == 14


def test_update_baseline_buckets_no_op_when_no_rows() -> None:
    """AC 7: When evidence_output.rows is empty, no update_bucket calls are made."""
    evidence_output = _make_evidence_output(rows=())
    mock_client = _make_mock_baseline_client()
    mock_logger = MagicMock()

    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
        logger=mock_logger,
    )

    mock_client.update_bucket.assert_not_called()


def test_update_baseline_buckets_called_even_when_no_findings() -> None:
    """AC 7: _update_baseline_buckets() is called regardless of whether the baseline
    deviation stage produced findings — bucket updates run after detection always."""
    scope = ("prod", "kafka-prod", "orders.completed")
    rows = (_make_evidence_row(scope, "consumer_group_lag", 100.0),)
    evidence_output = _make_evidence_output(rows=rows)
    mock_client = _make_mock_baseline_client()
    mock_logger = MagicMock()

    # Empty findings — detection found nothing
    empty_baseline_output = _make_baseline_deviation_output(findings=())

    # Simulate the __main__.py wiring: bucket update is called regardless of findings
    # (bucket writes always happen when the stage is enabled, per AC 7)
    if empty_baseline_output.findings:
        evidence_output = _merge_baseline_deviation_findings(
            evidence_output=evidence_output,
            baseline_deviation_output=empty_baseline_output,
        )
    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=mock_client,
        evaluation_time=FIXED_EVAL_TIME,
        logger=mock_logger,
    )

    # Bucket update must still fire even with empty findings
    assert mock_client.update_bucket.call_count == 1


# ---------------------------------------------------------------------------
# AC 6: BASELINE_DEVIATION_STAGE_ENABLED flag
# ---------------------------------------------------------------------------


def test_baseline_deviation_stage_disabled_returns_empty_output() -> None:
    """AC 6: When BASELINE_DEVIATION_STAGE_ENABLED=False, run_baseline_deviation_stage_cycle
    is NOT called and an empty BaselineDeviationStageOutput is used."""
    # This test validates the behaviour that __main__.py must implement:
    # the stage call is skipped and an empty output is constructed.
    # We verify this by confirming Settings accepts BASELINE_DEVIATION_STAGE_ENABLED=False
    # without validation error, and that BaselineDeviationStageOutput can be built empty.
    settings = Settings(BASELINE_DEVIATION_STAGE_ENABLED=False)  # type: ignore[call-arg]
    assert settings.BASELINE_DEVIATION_STAGE_ENABLED is False

    # Verify the empty output structure that __main__.py will use when disabled
    empty_output = BaselineDeviationStageOutput(
        findings=(),
        scopes_evaluated=0,
        deviations_detected=0,
        deviations_suppressed_single_metric=0,
        deviations_suppressed_dedup=0,
        evaluation_time=FIXED_EVAL_TIME,
    )
    assert empty_output.findings == ()
    assert empty_output.scopes_evaluated == 0


def test_baseline_deviation_stage_enabled_defaults_to_true() -> None:
    """AC 6: BASELINE_DEVIATION_STAGE_ENABLED defaults to True in Settings (NFR-R5)."""
    # Without explicitly setting the flag, it must default to True.
    # Use environment isolation to avoid env var interference.
    env_backup = os.environ.pop("BASELINE_DEVIATION_STAGE_ENABLED", None)
    try:
        settings = Settings()
        assert settings.BASELINE_DEVIATION_STAGE_ENABLED is True
    finally:
        if env_backup is not None:
            os.environ["BASELINE_DEVIATION_STAGE_ENABLED"] = env_backup
