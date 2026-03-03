import io
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.rulebook import (
    GateCheck,
    GateEffects,
    GateSpec,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
)
from aiops_triage_pipeline.models.anomaly import AnomalyFinding
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.models.peak import (
    PeakClassification,
    PeakProfile,
    PeakStageOutput,
    PeakWindowContext,
    SustainedStatus,
    SustainedWindowState,
)
from aiops_triage_pipeline.pipeline.stages.peak import (
    build_sustained_window_state_by_key,
    collect_peak_stage_output,
    load_peak_policy,
    load_redis_ttl_policy,
    load_rulebook_policy,
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


def test_load_rulebook_policy_from_default_path() -> None:
    policy = load_rulebook_policy()

    assert policy.schema_version == "v1"
    assert policy.sustained_intervals_required == 5


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


def _finding(
    *,
    scope: tuple[str, ...],
    anomaly_family: Literal[
        "CONSUMER_LAG",
        "VOLUME_DROP",
        "THROUGHPUT_CONSTRAINED_PROXY",
    ] = "VOLUME_DROP",
) -> AnomalyFinding:
    return AnomalyFinding(
        finding_id=f"{anomaly_family}:{'|'.join(scope)}",
        anomaly_family=anomaly_family,
        scope=scope,
        severity="MEDIUM",
        reason_codes=("DETECTED",),
        evidence_required=("topic_messages_in_per_sec",),
        is_primary=True,
    )


def _rulebook_policy_for_tests(required: int = 5) -> RulebookV1:
    defaults = RulebookDefaults(
        missing_series_policy="UNKNOWN_NOT_ZERO",
        required_evidence_policy="PRESENT_ONLY",
        missing_confidence_policy="DOWNGRADE",
        missing_sustained_policy="DOWNGRADE",
    )
    caps = RulebookCaps(
        max_action_by_env={"local": "OBSERVE", "dev": "OBSERVE", "stage": "NOTIFY", "prod": "PAGE"},
        max_action_by_tier_in_prod={
            "TIER_0": "PAGE",
            "TIER_1": "TICKET",
            "TIER_2": "NOTIFY",
            "UNKNOWN": "NOTIFY",
        },
        paging_denied_topic_roles=("SOURCE_TOPIC",),
    )
    gates = tuple(
        GateSpec(
            id=gate_id,
            name=f"Gate {gate_id}",
            intent="test",
            effect=GateEffects(),
            checks=(GateCheck(check_id=f"{gate_id}_CHECK", type="always_pass"),),
        )
        for gate_id in ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    )
    return RulebookV1(
        rulebook_id="rulebook.v1",
        version=1,
        evaluation_interval_minutes=5,
        sustained_intervals_required=required,
        defaults=defaults,
        caps=caps,
        gates=gates,
    )


def _to_window_state_map(
    sustained_by_key: dict[tuple[str, str, str, str], SustainedStatus],
) -> dict[tuple[str, str, str, str], SustainedWindowState]:
    return build_sustained_window_state_by_key(sustained_by_key)


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


def test_collect_peak_stage_output_marks_sustained_true_at_exactly_five_buckets() -> None:
    policy = _peak_policy_for_tests()
    rulebook = _rulebook_policy_for_tests(required=5)
    scope = ("prod", "cluster-a", "orders")
    finding = _finding(scope=scope, anomaly_family="VOLUME_DROP")
    prior: dict[tuple[str, str, str, str], SustainedWindowState] = {}
    evaluation_time = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    cycle4: PeakStageOutput | None = None
    cycle5: PeakStageOutput | None = None
    for _ in range(5):
        output = collect_peak_stage_output(
            rows=[],
            historical_windows_by_scope={},
            anomaly_findings=[finding],
            prior_sustained_window_state_by_key=prior,
            peak_policy=policy,
            rulebook_policy=rulebook,
            evaluation_time=evaluation_time,
        )
        if output.sustained_by_key:
            key = ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")
            assert key in output.sustained_by_key
        if evaluation_time == datetime(2026, 3, 2, 12, 15, tzinfo=UTC):
            cycle4 = output
        if evaluation_time == datetime(2026, 3, 2, 12, 20, tzinfo=UTC):
            cycle5 = output
        prior = _to_window_state_map(dict(output.sustained_by_key))
        evaluation_time += timedelta(minutes=5)

    assert cycle4 is not None
    assert cycle5 is not None
    key = ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")
    assert cycle4.sustained_by_key[key].consecutive_anomalous_buckets == 4
    assert cycle4.sustained_by_key[key].is_sustained is False
    assert cycle5.sustained_by_key[key].consecutive_anomalous_buckets == 5
    assert cycle5.sustained_by_key[key].is_sustained is True


def test_collect_peak_stage_output_resets_streak_after_non_anomalous_gap() -> None:
    policy = _peak_policy_for_tests()
    rulebook = _rulebook_policy_for_tests(required=5)
    scope = ("prod", "cluster-a", "orders")
    finding = _finding(scope=scope, anomaly_family="VOLUME_DROP")
    prior: dict[tuple[str, str, str, str], SustainedWindowState] = {}
    key = ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")

    first = collect_peak_stage_output(
        rows=[],
        historical_windows_by_scope={},
        anomaly_findings=[finding],
        prior_sustained_window_state_by_key=prior,
        peak_policy=policy,
        rulebook_policy=rulebook,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )
    prior = _to_window_state_map(dict(first.sustained_by_key))

    gap = collect_peak_stage_output(
        rows=[],
        historical_windows_by_scope={},
        anomaly_findings=[],
        prior_sustained_window_state_by_key=prior,
        peak_policy=policy,
        rulebook_policy=rulebook,
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )
    prior = _to_window_state_map(dict(gap.sustained_by_key))

    resumed = collect_peak_stage_output(
        rows=[],
        historical_windows_by_scope={},
        anomaly_findings=[finding],
        prior_sustained_window_state_by_key=prior,
        peak_policy=policy,
        rulebook_policy=rulebook,
        evaluation_time=datetime(2026, 3, 2, 12, 10, tzinfo=UTC),
    )

    assert first.sustained_by_key[key].consecutive_anomalous_buckets == 1
    assert gap.sustained_by_key[key].consecutive_anomalous_buckets == 0
    assert resumed.sustained_by_key[key].consecutive_anomalous_buckets == 1
    assert resumed.sustained_by_key[key].is_sustained is False


def test_collect_peak_stage_output_tracks_independent_sustained_keys() -> None:
    policy = _peak_policy_for_tests()
    rulebook = _rulebook_policy_for_tests(required=5)
    key_a = ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")
    key_b = ("prod", "cluster-a", "group:payments-worker", "CONSUMER_LAG")
    finding_a = _finding(scope=("prod", "cluster-a", "orders"), anomaly_family="VOLUME_DROP")
    finding_b = _finding(
        scope=("prod", "cluster-a", "payments-worker", "payments"),
        anomaly_family="CONSUMER_LAG",
    )

    cycle1 = collect_peak_stage_output(
        rows=[],
        historical_windows_by_scope={},
        anomaly_findings=[finding_a, finding_b],
        prior_sustained_window_state_by_key={},
        peak_policy=policy,
        rulebook_policy=rulebook,
        evaluation_time=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
    )
    cycle2 = collect_peak_stage_output(
        rows=[],
        historical_windows_by_scope={},
        anomaly_findings=[finding_a],
        prior_sustained_window_state_by_key=_to_window_state_map(dict(cycle1.sustained_by_key)),
        peak_policy=policy,
        rulebook_policy=rulebook,
        evaluation_time=datetime(2026, 3, 2, 12, 5, tzinfo=UTC),
    )

    assert cycle1.sustained_by_key[key_a].consecutive_anomalous_buckets == 1
    assert cycle1.sustained_by_key[key_b].consecutive_anomalous_buckets == 1
    assert cycle2.sustained_by_key[key_a].consecutive_anomalous_buckets == 2
    assert cycle2.sustained_by_key[key_b].consecutive_anomalous_buckets == 0
