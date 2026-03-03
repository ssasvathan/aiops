import io
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.models.peak import (
    PeakClassification,
    PeakProfile,
    PeakStageOutput,
    PeakWindowContext,
)
from aiops_triage_pipeline.pipeline.stages.peak import (
    collect_peak_stage_output,
    load_peak_policy,
    load_redis_ttl_policy,
)


def test_peak_profile_is_frozen() -> None:
    profile = PeakProfile(
        scope=("prod", "cluster-a", "orders"),
        source_metric="kafka_server_brokertopicmetrics_messagesinpersec",
        peak_threshold_value=250.0,
        near_peak_threshold_value=200.0,
        history_samples_count=14,
        has_sufficient_history=True,
        recompute_frequency="weekly",
        computed_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(ValidationError):
        profile.peak_threshold_value = 300.0  # type: ignore[misc]


def test_peak_classification_supports_unknown_state() -> None:
    classification = PeakClassification(
        scope=("dev", "cluster-1", "payments"),
        state="UNKNOWN",
        current_value=None,
        confidence=0.0,
        reason_codes=("MISSING_REQUIRED_SERIES",),
        is_peak_window=False,
        is_near_peak_window=False,
        peak_threshold_value=None,
        near_peak_threshold_value=None,
    )

    assert classification.state == "UNKNOWN"


def test_peak_stage_output_maps_are_immutable() -> None:
    scope = ("prod", "cluster-a", "orders")
    context = PeakWindowContext(
        classification="OFF_PEAK",
        is_peak_window=False,
        is_near_peak_window=False,
        confidence=1.0,
        reason_codes=("CLASSIFIED_FROM_BASELINE",),
    )
    output = PeakStageOutput(
        profiles_by_scope={},
        classifications_by_scope={},
        peak_context_by_scope={scope: context},
    )

    with pytest.raises(TypeError):
        output.peak_context_by_scope[scope] = context


def test_load_peak_policy_from_default_path() -> None:
    policy = load_peak_policy()

    assert policy.schema_version == "v1"
    assert policy.recompute_frequency == "weekly"
    assert policy.defaults.peak_percentile == 90
    assert policy.defaults.near_peak_percentile == 95


def test_load_redis_ttl_policy_from_default_path() -> None:
    policy = load_redis_ttl_policy()

    assert policy.schema_version == "v1"
    assert policy.ttls_by_env["prod"].peak_profile_seconds == 86400


def _peak_policy_for_tests() -> PeakPolicyV1:
    return PeakPolicyV1(
        metric="kafka_server_brokertopicmetrics_messagesinpersec",
        timezone="America/Toronto",
        recompute_frequency="weekly",
        defaults=PeakThresholdPolicy(
            peak_percentile=90,
            near_peak_percentile=95,
            bucket_minutes=15,
            min_baseline_windows=4,
        ),
    )


def _row(scope: tuple[str, ...], metric_key: str, value: float) -> EvidenceRow:
    labels = {
        "env": scope[0],
        "cluster_id": scope[1],
        "topic": scope[-1],
    }
    if len(scope) == 4:
        labels["group"] = scope[2]
    return EvidenceRow(metric_key=metric_key, value=value, labels=labels, scope=scope)


def test_collect_peak_stage_output_classifies_peak_near_peak_off_peak_boundaries() -> None:
    policy = _peak_policy_for_tests()
    scope = ("prod", "cluster-a", "orders")
    rows = [
        _row(scope, "topic_messages_in_per_sec", 19.0),
        _row(("prod", "cluster-a", "consumer-a", "orders"), "consumer_group_lag", 10.0),
    ]
    # history = [1.0 .. 20.0] (20 samples)
    # peak_threshold     = p95([1..20]) = nearest_rank(0.95*20=19) = values[18] = 19
    # near_peak_threshold = p90([1..20]) = nearest_rank(0.90*20=18) = values[17] = 18
    history = {scope: [float(x) for x in range(1, 21)]}

    peak_output = collect_peak_stage_output(
        rows=rows,
        historical_windows_by_scope=history,
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    peak = peak_output.classifications_by_scope[scope]
    assert peak.state == "PEAK"
    assert peak.is_peak_window is True
    assert peak.is_near_peak_window is True

    near_output = collect_peak_stage_output(
        rows=[_row(scope, "topic_messages_in_per_sec", 18.0)],
        historical_windows_by_scope=history,
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )
    near = near_output.classifications_by_scope[scope]
    assert near.state == "NEAR_PEAK"
    assert near.is_peak_window is False
    assert near.is_near_peak_window is True

    off_output = collect_peak_stage_output(
        rows=[_row(scope, "topic_messages_in_per_sec", 17.0)],
        historical_windows_by_scope=history,
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )
    off = off_output.classifications_by_scope[scope]
    assert off.state == "OFF_PEAK"
    assert off.is_peak_window is False
    assert off.is_near_peak_window is False


def test_collect_peak_stage_output_uses_low_confidence_fallback_for_insufficient_history() -> None:
    policy = _peak_policy_for_tests()
    scope = ("dev", "cluster-a", "orders")

    output = collect_peak_stage_output(
        rows=[_row(scope, "topic_messages_in_per_sec", 40.0)],
        historical_windows_by_scope={scope: [10.0, 20.0]},
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    classification = output.classifications_by_scope[scope]
    assert classification.confidence < 1.0
    assert "INSUFFICIENT_HISTORY" in classification.reason_codes


def test_collect_peak_stage_output_preserves_unknown_for_missing_required_series() -> None:
    policy = _peak_policy_for_tests()
    lag_scope = ("prod", "cluster-z", "consumer-a", "payments")
    topic_scope = ("prod", "cluster-z", "payments")

    output = collect_peak_stage_output(
        rows=[_row(lag_scope, "consumer_group_lag", 250.0)],
        historical_windows_by_scope={topic_scope: [100.0, 101.0, 102.0, 103.0]},
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    classification = output.classifications_by_scope[topic_scope]
    assert classification.state == "UNKNOWN"
    assert classification.current_value is None
    assert "MISSING_REQUIRED_SERIES" in classification.reason_codes


def test_collect_peak_stage_output_is_deterministic_for_identical_inputs() -> None:
    policy = _peak_policy_for_tests()
    scope = ("prod", "cluster-a", "orders")
    rows = [
        _row(scope, "topic_messages_in_per_sec", 18.0),
        _row(scope, "topic_messages_in_per_sec", 17.0),
    ]
    history = {scope: [float(x) for x in range(1, 21)]}

    output_a = collect_peak_stage_output(
        rows=rows,
        historical_windows_by_scope=history,
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )
    output_b = collect_peak_stage_output(
        rows=rows,
        historical_windows_by_scope=history,
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    assert output_a == output_b
    context = output_a.peak_context_by_scope[scope]
    # max(18.0, 17.0) = 18; p90([1..20]) = 18 (near_peak), p95([1..20]) = 19 (peak)
    # 18 >= near_peak(18) and 18 < peak(19) → NEAR_PEAK
    assert context.classification == "NEAR_PEAK"


def _parse_logs(stream: io.StringIO) -> list[dict]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_collect_peak_stage_output_warns_for_malformed_scope(
    log_stream: io.StringIO,
) -> None:
    policy = _peak_policy_for_tests()
    # 2-element scope: _to_topic_scope returns None → warning + skip
    malformed_scope = ("prod", "cluster-a")

    output = collect_peak_stage_output(
        rows=[_row(malformed_scope, "topic_messages_in_per_sec", 18.0)],
        historical_windows_by_scope={},
        peak_policy=policy,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )

    assert dict(output.classifications_by_scope) == {}
    warning_events = [
        entry
        for entry in _parse_logs(log_stream)
        if entry.get("event") == "peak_scope_normalization_failed"
    ]
    assert len(warning_events) == 1
    assert warning_events[0]["event_type"] == "peak.scope_normalization_warning"
