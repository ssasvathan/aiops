"""PeakPolicyV1 — system-wide peak/near-peak classification defaults."""

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, field_validator

_RecomputeFrequency = Literal["daily", "weekly", "monthly"]


class PeakThresholdPolicy(BaseModel, frozen=True):
    peak_percentile: int = 90
    near_peak_percentile: int = 95
    bucket_minutes: int = 15
    min_baseline_windows: int = 4


class PeakPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    metric: str
    timezone: str
    recompute_frequency: _RecomputeFrequency
    defaults: PeakThresholdPolicy

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Unknown IANA timezone: {value!r}")
        return value
