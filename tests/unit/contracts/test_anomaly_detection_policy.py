"""Unit tests for AnomalyDetectionPolicyV1 contract and artifact loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1
from aiops_triage_pipeline.pipeline.stages.anomaly import (
    _LAG_BUILDUP_MAX_OFFSET_PROGRESS,
    _LAG_BUILDUP_MIN_GROWTH,
    _LAG_BUILDUP_MIN_LAG,
    _THROUGHPUT_FAILURE_RATIO_MIN,
    _THROUGHPUT_MIN_MESSAGES_PER_SEC,
    _THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC,
    _VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC,
    _VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC,
    _VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC,
)


def test_default_values_match_anomaly_stage_constants() -> None:
    policy = AnomalyDetectionPolicyV1()
    assert policy.lag_buildup_min_lag == _LAG_BUILDUP_MIN_LAG
    assert policy.lag_buildup_min_growth == _LAG_BUILDUP_MIN_GROWTH
    assert policy.lag_buildup_max_offset_progress == _LAG_BUILDUP_MAX_OFFSET_PROGRESS
    assert policy.throughput_min_messages_per_sec == _THROUGHPUT_MIN_MESSAGES_PER_SEC
    assert (
        policy.throughput_min_total_produce_requests_per_sec
        == _THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC
    )
    assert policy.throughput_failure_ratio_min == _THROUGHPUT_FAILURE_RATIO_MIN
    assert (
        policy.volume_drop_max_current_messages_in_per_sec
        == _VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC
    )
    assert (
        policy.volume_drop_min_baseline_messages_in_per_sec
        == _VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC
    )
    assert (
        policy.volume_drop_min_expected_requests_per_sec
        == _VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC
    )


def test_invalid_threshold_raises() -> None:
    with pytest.raises(ValidationError):
        AnomalyDetectionPolicyV1(lag_buildup_min_lag=-1.0)

    with pytest.raises(ValidationError):
        AnomalyDetectionPolicyV1(lag_buildup_min_lag=0.0)

    with pytest.raises(ValidationError):
        AnomalyDetectionPolicyV1(volume_drop_max_current_messages_in_per_sec=0.0)


def test_failure_ratio_out_of_range_raises() -> None:
    with pytest.raises(ValidationError):
        AnomalyDetectionPolicyV1(throughput_failure_ratio_min=1.1)

    with pytest.raises(ValidationError):
        AnomalyDetectionPolicyV1(throughput_failure_ratio_min=0.0)

    with pytest.raises(ValidationError):
        AnomalyDetectionPolicyV1(throughput_failure_ratio_min=-0.1)


def test_load_policy_yaml_roundtrip() -> None:
    policy_path = (
        Path(__file__).resolve().parents[3]
        / "config/policies/anomaly-detection-policy-v1.yaml"
    )
    policy = load_policy_yaml(policy_path, AnomalyDetectionPolicyV1)

    assert isinstance(policy, AnomalyDetectionPolicyV1)
    assert policy.schema_version == "v1"
    assert policy.policy_id == "anomaly-detection-policy-v1"
    assert policy.lag_buildup_min_lag == _LAG_BUILDUP_MIN_LAG
    assert policy.lag_buildup_min_growth == _LAG_BUILDUP_MIN_GROWTH
    assert policy.lag_buildup_max_offset_progress == _LAG_BUILDUP_MAX_OFFSET_PROGRESS
    assert policy.throughput_min_messages_per_sec == _THROUGHPUT_MIN_MESSAGES_PER_SEC
    assert (
        policy.throughput_min_total_produce_requests_per_sec
        == _THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC
    )
    assert policy.throughput_failure_ratio_min == _THROUGHPUT_FAILURE_RATIO_MIN
    assert (
        policy.volume_drop_max_current_messages_in_per_sec
        == _VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC
    )
    assert (
        policy.volume_drop_min_baseline_messages_in_per_sec
        == _VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC
    )
    assert (
        policy.volume_drop_min_expected_requests_per_sec
        == _VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC
    )
