"""AnomalyDetectionPolicyV1 — anomaly detector threshold policy contract."""

from typing import Literal

from pydantic import BaseModel, field_validator


class AnomalyDetectionPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    policy_id: Literal["anomaly-detection-policy-v1"] = "anomaly-detection-policy-v1"

    lag_buildup_min_lag: float = 100.0
    lag_buildup_min_growth: float = 25.0
    lag_buildup_max_offset_progress: float = 10.0
    throughput_min_messages_per_sec: float = 1000.0
    throughput_min_total_produce_requests_per_sec: float = 100.0
    throughput_failure_ratio_min: float = 0.05
    volume_drop_max_current_messages_in_per_sec: float = 1.0
    volume_drop_min_baseline_messages_in_per_sec: float = 50.0
    volume_drop_min_expected_requests_per_sec: float = 150.0

    @field_validator(
        "lag_buildup_min_lag",
        "lag_buildup_min_growth",
        "lag_buildup_max_offset_progress",
        "throughput_min_messages_per_sec",
        "throughput_min_total_produce_requests_per_sec",
        "volume_drop_max_current_messages_in_per_sec",
        "volume_drop_min_baseline_messages_in_per_sec",
        "volume_drop_min_expected_requests_per_sec",
    )
    @classmethod
    def _validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("threshold must be > 0")
        return value

    @field_validator("throughput_failure_ratio_min")
    @classmethod
    def _validate_failure_ratio(cls, value: float) -> float:
        if not (0.0 < value <= 1.0):
            raise ValueError("throughput_failure_ratio_min must be in (0.0, 1.0]")
        return value
